import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd


class DataManager:
    def __init__(self, uploads_dir: str = 'uploads'):
        if os.path.isabs(uploads_dir):
            self.uploads_dir = uploads_dir
        else:
            self.uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), uploads_dir)
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        self.transactions_file = os.path.join(self.data_dir, 'transactions.json')
        self.sheet_data_file = os.path.join(self.data_dir, 'sheet_data.json')

    def load_transactions_from_json(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.transactions_file):
            return []
        with open(self.transactions_file, 'r') as f:
            return json.load(f)
        
    def save_transactions(self, transactions: List[Dict[str, Any]]):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self.transactions_file, 'w') as f:
            json.dump(transactions, f, indent=2)
    
    def load_transactions(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.transactions_file):
            with open(self.transactions_file, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        return []
    
    def save_sheet_data(self, sheet_data: Dict[str, Any]):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self.sheet_data_file, 'w') as f:
            json.dump(sheet_data, f, indent=2)
    
    def load_sheet_data(self) -> Dict[str, Any]:
        if os.path.exists(self.sheet_data_file):
            with open(self.sheet_data_file, 'r') as f:
                return json.load(f)
        return {}
    
    def parse_sheet(self, file_path: str) -> Dict[str, Any]:
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.csv':
            df = pd.read_csv(file_path)
        elif file_ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")
        
        result = {
            'columns': list(df.columns),
            'rows': df.to_dict('records'),
            'total_rows': len(df)
        }
        
        for col in df.columns:
            col_lower = col.lower()
            if 'cashback' in col_lower or 'reward' in col_lower:
                result['cashback_column'] = col
            if 'issuer' in col_lower or 'card' in col_lower or 'bank' in col_lower:
                result['issuer_column'] = col
            if 'date' in col_lower:
                result['date_column'] = col
        
        return result
    
    def get_organized_data(self, transactions: List[Dict[str, Any]], sheet_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        organized = {
            'by_issuer': {},
            'by_month': {},
            'by_issuer_and_month': {},
            'summary': {
                'total_transactions': len(transactions),
                'dr_transactions': 0,
                'cr_transactions': 0,
                'total_spend': 0.0,
                'total_calculated_cashback': 0.0,
                'total_stated_cashback': 0.0,
                'match_count': 0,
                'mismatch_count': 0
            }
        }
        
        for trans in transactions:
            issuer = trans.get('card_issuer', 'Unknown')
            date_str = trans.get('date', '')
            trans_type = trans.get('transaction_type', 'DR')
            is_credit = trans_type == 'CR' or trans.get('is_credit', False)
            
            if is_credit:
                organized['summary']['cr_transactions'] += 1
            else:
                organized['summary']['dr_transactions'] += 1
            
            try:
                if '/' in date_str:
                    dt = datetime.strptime(date_str, '%d/%m/%Y')
                else:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                month_key = dt.strftime('%Y-%m')
                month_display = dt.strftime('%B %Y')
            except:
                month_key = 'unknown'
                month_display = 'Unknown'
            
            if issuer not in organized['by_issuer']:
                organized['by_issuer'][issuer] = {
                    'transactions': [],
                    'total_spend': 0.0,
                    'total_cashback': 0.0,
                    'by_month': {}
                }
            
            organized['by_issuer'][issuer]['transactions'].append(trans)
            
            if not is_credit:
                organized['by_issuer'][issuer]['total_spend'] += abs(trans.get('amount', 0))
                organized['by_issuer'][issuer]['total_cashback'] += trans.get('calculated_cashback', 0)
            
            if month_key not in organized['by_issuer'][issuer]['by_month']:
                organized['by_issuer'][issuer]['by_month'][month_key] = {
                    'display': month_display,
                    'transactions': [],
                    'total_spend': 0.0,
                    'total_cashback': 0.0
                }
            
            organized['by_issuer'][issuer]['by_month'][month_key]['transactions'].append(trans)
            
            if not is_credit:
                organized['by_issuer'][issuer]['by_month'][month_key]['total_spend'] += abs(trans.get('amount', 0))
                organized['by_issuer'][issuer]['by_month'][month_key]['total_cashback'] += trans.get('calculated_cashback', 0)
            
            if month_key not in organized['by_month']:
                organized['by_month'][month_key] = {
                    'display': month_display,
                    'by_issuer': {},
                    'transactions': [],
                    'total_spend': 0.0,
                    'total_cashback': 0.0
                }
            
            if issuer not in organized['by_month'][month_key]['by_issuer']:
                organized['by_month'][month_key]['by_issuer'][issuer] = {
                    'transactions': [],
                    'total_spend': 0.0,
                    'total_cashback': 0.0
                }
            
            organized['by_month'][month_key]['by_issuer'][issuer]['transactions'].append(trans)
            organized['by_month'][month_key]['transactions'].append(trans)
            
            if not is_credit:
                organized['by_month'][month_key]['by_issuer'][issuer]['total_spend'] += abs(trans.get('amount', 0))
                organized['by_month'][month_key]['by_issuer'][issuer]['total_cashback'] += trans.get('calculated_cashback', 0)
                organized['by_month'][month_key]['total_spend'] += abs(trans.get('amount', 0))
                organized['by_month'][month_key]['total_cashback'] += trans.get('calculated_cashback', 0)
            
            key = f"{issuer}_{month_key}"
            if key not in organized['by_issuer_and_month']:
                organized['by_issuer_and_month'][key] = {
                    'issuer': issuer,
                    'month': month_key,
                    'display': f"{issuer} - {month_display}",
                    'transactions': [],
                    'total_spend': 0.0,
                    'total_cashback': 0.0
                }
            
            organized['by_issuer_and_month'][key]['transactions'].append(trans)
            
            if not is_credit:
                organized['by_issuer_and_month'][key]['total_spend'] += abs(trans.get('amount', 0))
                organized['by_issuer_and_month'][key]['total_cashback'] += trans.get('calculated_cashback', 0)
                organized['summary']['total_spend'] += abs(trans.get('amount', 0))
                organized['summary']['total_calculated_cashback'] += trans.get('calculated_cashback', 0)
        
        organized['summary']['total_spend'] = round(organized['summary']['total_spend'], 2)
        organized['summary']['total_calculated_cashback'] = round(organized['summary']['total_calculated_cashback'], 2)
        
        for issuer in organized['by_issuer']:
            organized['by_issuer'][issuer]['total_spend'] = round(organized['by_issuer'][issuer]['total_spend'], 2)
            organized['by_issuer'][issuer]['total_cashback'] = round(organized['by_issuer'][issuer]['total_cashback'], 2)
        
        for month_key in organized['by_month']:
            organized['by_month'][month_key]['total_spend'] = round(organized['by_month'][month_key]['total_spend'], 2)
            organized['by_month'][month_key]['total_cashback'] = round(organized['by_month'][month_key]['total_cashback'], 2)
        
        if sheet_data:
            self._compare_with_sheet(organized, sheet_data)
        
        return organized
    
    def _compare_with_sheet(self, organized: Dict[str, Any], sheet_data: Dict[str, Any]):
        if 'rows' not in sheet_data or not sheet_data['rows']:
            return
        
        sheet_transactions = sheet_data['rows']
        issuer_col = sheet_data.get('issuer_column', '')
        date_col = sheet_data.get('date_column', '')
        cashback_col = sheet_data.get('cashback_column', '')
        
        sheet_cashback_by_issuer = {}
        sheet_cashback_total = 0.0
        
        for row in sheet_transactions:
            issuer = row.get(issuer_col, 'Unknown') if issuer_col else 'Unknown'
            stated_cashback = 0.0
            
            if cashback_col and cashback_col in row:
                try:
                    val = str(row[cashback_col]).replace('$', '').replace(',', '')
                    stated_cashback = float(val)
                except:
                    stated_cashback = 0.0
            
            if issuer not in sheet_cashback_by_issuer:
                sheet_cashback_by_issuer[issuer] = 0.0
            sheet_cashback_by_issuer[issuer] += stated_cashback
            sheet_cashback_total += stated_cashback
        
        organized['summary']['total_stated_cashback'] = round(sheet_cashback_total, 2)
        organized['sheet_data'] = sheet_data
        organized['comparison'] = {
            'by_issuer': {},
            'overall': self._calculate_match(
                organized['summary']['total_calculated_cashback'],
                sheet_cashback_total
            )
        }
        
        for issuer in organized['by_issuer']:
            calc_cashback = organized['by_issuer'][issuer]['total_cashback']
            stated_cashback = sheet_cashback_by_issuer.get(issuer, 0.0)
            
            organized['comparison']['by_issuer'][issuer] = self._calculate_match(
                calc_cashback, stated_cashback
            )
            
            if organized['comparison']['by_issuer'][issuer]['match']:
                organized['summary']['match_count'] += 1
            else:
                organized['summary']['mismatch_count'] += 1
        
        organized['summary']['overall_match'] = organized['comparison']['overall']['match']
    
    def _calculate_match(self, calculated: float, stated: float, tolerance: float = 1.0) -> Dict[str, Any]:
        difference = calculated - stated
        percent_diff = (difference / stated * 100) if stated != 0 else 0
        
        return {
            'calculated': round(calculated, 2),
            'stated': round(stated, 2),
            'difference': round(difference, 2),
            'percent_difference': round(abs(percent_diff), 2),
            'match': abs(difference) <= tolerance,
            'status': 'Match' if abs(difference) <= tolerance else 'Mismatch'
        }
    
    def clear_data(self):
        if os.path.exists(self.transactions_file):
            os.remove(self.transactions_file)
        with open(self.transactions_file, 'w') as f:
            json.dump([], f)
        if os.path.exists(self.sheet_data_file):
            os.remove(self.sheet_data_file)
