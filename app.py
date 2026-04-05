from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json

from backend.pdf_parser import PDFParser
from backend.cashback_calculator import CashbackCalculator
from backend.data_manager import DataManager

BASE_DIR = os.path.dirname(__file__)
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'static'))
CORS(app)

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

data_manager = DataManager(UPLOAD_FOLDER)
pdf_parser = PDFParser()
cashback_calculator = CashbackCalculator()

_cached_organized_data = None
_cached_transactions = None


@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/upload-pdf', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.lower().endswith('.pdf'):
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        already_exists = os.path.exists(filepath)
        
        if not already_exists:
            file.save(filepath)
        
        pdf_parser.unlock_pdf(filepath)
        
        try:
            existing_transactions = data_manager.load_transactions()
            
            if already_exists and existing_transactions:
                return jsonify({
                    'success': True,
                    'message': f'{file.filename} already processed. Using existing {len(existing_transactions)} transactions.',
                    'transactions_count': 0,
                    'total_transactions': len(existing_transactions),
                    'skipped': True
                })
            
            new_transactions = pdf_parser.extract_transactions(filepath)
            
            all_transactions = existing_transactions + new_transactions
            
            cashback_results = cashback_calculator.calculate_total_cashback(all_transactions)
            
            data_manager.save_transactions(cashback_results['transactions'])
            
            return jsonify({
                'success': True,
                'message': f'Processed {len(new_transactions)} transactions from {file.filename}. Total: {len(all_transactions)}',
                'transactions_count': len(new_transactions),
                'total_transactions': len(all_transactions),
                'summary': {
                    'total_spend': cashback_results['total_spend'],
                    'total_cashback': cashback_results['total_cashback'],
                    'by_category': cashback_results['by_category'],
                    'by_issuer': cashback_results['by_issuer'],
                    'by_month': cashback_results['by_month']
                }
            })
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500
    
    return jsonify({'error': 'Invalid file type'}), 400


@app.route('/api/reload-data', methods=['POST'])
def reload_data():
    try:
        force = request.args.get('force', 'false').lower() == 'true'
        
        transactions = data_manager.load_transactions()
        
        if force or not transactions:
            pdf_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith('.pdf')]
            
            if not pdf_files:
                data_manager.save_transactions([])
                return jsonify({
                    'success': True,
                    'message': 'No PDF files found',
                    'total_transactions': 0
                })
            
            all_transactions = []
            seen_keys = set()
            
            for pdf_file in pdf_files:
                filepath = os.path.join(UPLOAD_FOLDER, pdf_file)
                pdf_parser.unlock_pdf(filepath)
                transactions = pdf_parser.extract_transactions(filepath)
                
                for trans in transactions:
                    key = f"{trans['date']}_{trans['description'][:30]}_{trans['amount']}_{trans.get('transaction_type', 'DR')}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_transactions.append(trans)
            
            all_transactions.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            cashback_results = cashback_calculator.calculate_total_cashback(all_transactions)
            
            data_manager.save_transactions(cashback_results['transactions'])
            global _cached_organized_data, _cached_transactions
            _cached_organized_data = None
            _cached_transactions = None
            
            return jsonify({
                'success': True,
                'message': f'Reloaded {len(pdf_files)} PDF(s), {len(all_transactions)} transactions',
                'total_transactions': len(all_transactions),
                'summary': {
                    'total_spend': cashback_results['total_spend'],
                    'total_cashback': cashback_results['total_cashback'],
                    'by_category': cashback_results['by_category'],
                    'by_issuer': cashback_results['by_issuer'],
                    'by_month': cashback_results['by_month']
                }
            })
        
        cashback_results = cashback_calculator.calculate_total_cashback(transactions)
        
        return jsonify({
            'success': True,
            'message': f'Loaded {len(transactions)} transactions from cache',
            'total_transactions': len(transactions),
            'summary': {
                'total_spend': cashback_results['total_spend'],
                'total_cashback': cashback_results['total_cashback'],
                'by_category': cashback_results['by_category'],
                'by_issuer': cashback_results['by_issuer'],
                'by_month': cashback_results['by_month']
            }
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/upload-sheet', methods=['POST'])
def upload_sheet():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ['.csv', '.xlsx', '.xls']:
        return jsonify({'error': 'Invalid file type'}), 400
    
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)
    
    try:
        sheet_data = data_manager.parse_sheet(filepath)
        data_manager.save_sheet_data(sheet_data)
        
        return jsonify({
            'success': True,
            'message': 'Sheet processed successfully',
            'data': sheet_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    global _cached_organized_data
    
    if _cached_organized_data is None:
        transactions = data_manager.load_transactions()
        sheet_data = data_manager.load_sheet_data()
        _cached_organized_data = data_manager.get_organized_data(transactions, sheet_data if sheet_data else None)
        _cached_organized_data['transactions'] = transactions
    
    return jsonify(_cached_organized_data)


@app.route('/api/transactions-count', methods=['GET'])
def get_transactions_count():
    transactions = data_manager.load_transactions()
    return jsonify({'count': len(transactions)})


@app.route('/api/debug', methods=['GET'])
def debug_info():
    transactions = data_manager.load_transactions()
    sheet_data = data_manager.load_sheet_data()
    
    return jsonify({
        'transactions_count': len(transactions),
        'transactions_sample': transactions[:5] if transactions else [],
        'sheet_data_exists': bool(sheet_data),
        'uploads_dir': UPLOAD_FOLDER,
        'uploads_files': os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else []
    })


@app.route('/api/test-pdf/<filename>', methods=['GET'])
def test_pdf(filename):
    import io
    import sys
    
    pdf_path = os.path.join(UPLOAD_FOLDER, filename)
    
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'File not found', 'path': pdf_path}), 404
    
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    
    try:
        transactions = pdf_parser.extract_transactions(pdf_path)
        output = buffer.getvalue()
        sys.stdout = old_stdout
        
        cashback_results = cashback_calculator.calculate_total_cashback(transactions)
        
        return jsonify({
            'success': True,
            'transactions_count': len(transactions),
            'dr_transactions': cashback_results.get('dr_transactions', 0),
            'cr_transactions': cashback_results.get('cr_transactions', 0),
            'transactions': transactions,
            'summary': {
                'total_spend': cashback_results['total_spend'],
                'total_cashback': cashback_results['total_cashback'],
                'by_category': cashback_results['by_category'],
                'by_issuer': cashback_results['by_issuer'],
                'by_month': cashback_results['by_month']
            },
            'debug_output': output
        })
    except Exception as e:
        sys.stdout = old_stdout
        return jsonify({
            'error': str(e),
            'debug_output': buffer.getvalue() if buffer else ''
        }), 500


@app.route('/api/transactions/csv', methods=['GET'])
def get_transactions_from_csv():
    try:
        transactions = data_manager.load_transactions_from_json()
        cashback_results = cashback_calculator.calculate_total_cashback(transactions)
        return jsonify({
            'success': True,
            'transactions': transactions,
            'count': len(transactions),
            'summary': {
                'total_spend': cashback_results['total_spend'],
                'total_cashback': cashback_results['total_cashback'],
                'by_category': cashback_results['by_category'],
                'by_issuer': cashback_results['by_issuer']
            }
        })
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/compare', methods=['GET'])
def compare_cashback():
    transactions = data_manager.load_transactions()
    sheet_data = data_manager.load_sheet_data()
    
    if not transactions:
        return jsonify({'error': 'No transactions found'}), 400
    
    cashback_results = cashback_calculator.calculate_total_cashback(transactions)
    
    if sheet_data and 'rows' in sheet_data:
        sheet_cashback = sum(
            float(str(row.get(sheet_data.get('cashback_column', ''), 0)).replace('$', '').replace(',', '') or 0)
            for row in sheet_data['rows']
        )
    else:
        sheet_cashback = 0
    
    comparison = cashback_calculator.compare_cashback(
        cashback_results['total_cashback'],
        sheet_cashback
    )
    
    return jsonify({
        'calculated_total': cashback_results['total_cashback'],
        'stated_total': sheet_cashback,
        'comparison': comparison,
        'by_issuer': cashback_results['by_issuer']
    })


@app.route('/api/clear', methods=['POST'])
def clear_data():
    global _cached_organized_data, _cached_transactions
    data_manager.clear_data()
    _cached_organized_data = None
    _cached_transactions = None
    return jsonify({'success': True, 'message': 'All data cleared'})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
