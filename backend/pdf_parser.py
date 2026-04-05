import pdfplumber
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

DATE_PATTERN = re.compile(r'^(\d{1,2}[/-]\d{1,2}[/-]\d{4})')
AMOUNT_PATTERN = re.compile(r'(\d{1,3}(?:,\d{3})*\.\d{2})\s+(Cr|Dr|CR|DR)?\s*$')
CATEGORY_KEYWORDS = ['RESTAURANTS', 'DEPT STORES', 'JEWELLERY', 'GROCERY', 'FUEL', 'TRAVEL', 'AIRLINES', 
                     'HOTELS', 'ONLINE', 'SHOPPING', 'ENTERTAINMENT', 'UTILITIES', 'PHARMACY']
SKIP_KEYWORDS = ['total', 'subtotal', 'balance', 'previous', 'statement', 
                 'opening', 'closing', 'available', 'minimum', 'interest', 'due date',
                 'credit limit', 'cash limit', 'reward point', 'schedule', 
                 'finance charge', 'particular', 'payment summary', 'account summary',
                 '****', '===', '---', 'txn date', 'type', 'cr/db', 'contribution']

STATEMENT_DATE_PATTERNS = [
    r'Statement\s+Generation\s+Date\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    r'statement\s*generation\s*date[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    r'Statement\s+Date\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    r'statement\s*date[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    r'Date\s+of\s+Statement\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    r'date\s*of\s*statement[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    r'Bill\s+Date\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    r'bill\s*date[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    r'generated\s*on[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
]


class PDFParser:
    PDF_PASSWORD = 'ESWA4148'
    
    def __init__(self):
        self.card_issuers = {
            'hdfc': ['hdfc', 'hdfc bank'],
            'icici': ['icici', 'icici bank'],
            'sbi': ['sbi', 'state bank', 'state bank of india'],
            'axis': ['axis', 'axis bank'],
            'kotak': ['kotak', 'kotak bank'],
            'yes_bank': ['yes bank', 'yesbank'],
            'pnb': ['punjab national bank', 'pnb'],
        }
    
    def unlock_pdf(self, pdf_path: str) -> bool:
        try:
            import pikepdf
            with pikepdf.open(pdf_path, password=self.PDF_PASSWORD, allow_overwriting_input=True) as pdf:
                if pdf.is_encrypted:
                    pdf.save(pdf_path, encryption=False)
                    return True
            return False
        except Exception as e:
            if 'password' in str(e).lower():
                try:
                    with pikepdf.open(pdf_path, password='', allow_overwriting_input=True) as pdf:
                        if pdf.is_encrypted:
                            pdf.save(pdf_path, encryption=False)
                        return True
                except:
                    pass
            return False
    
    def _open_pdf(self, pdf_path: str):
        try:
            return pdfplumber.open(pdf_path)
        except Exception as e:
            if 'password' in str(e).lower() or 'encrypted' in str(e).lower():
                return pdfplumber.open(pdf_path, password=self.PDF_PASSWORD)
            raise e
        
    def identify_card_issuer(self, text: str) -> str:
        text_lower = text.lower()
        
        priority_phrases = [
            ('axis bank', 'axis'),
            ('hdfc bank', 'hdfc'),
            ('icici bank', 'icici'),
            ('state bank of india', 'sbi'),
            ('kotak bank', 'kotak'),
            ('yes bank', 'yes_bank'),
            ('punjab national bank', 'pnb'),
            ('american express', 'amex'),
            ('capital one', 'capital_one'),
            ('chase sapphire', 'chase'),
            ('bank of america', 'bank_of_america'),
        ]
        
        for phrase, issuer_key in priority_phrases:
            if phrase in text_lower:
                return issuer_key.replace('_', ' ').title()
        
        return 'Unknown'
    
    def extract_transactions(self, pdf_path: str) -> List[Dict[str, Any]]:
        transactions = []
        seen = set()
        statement_date = None
        cashback_details = {'cashback_earned': 0.0, 'cashback_credited': 0.0}
        
        with self._open_pdf(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            card_issuer = self.identify_card_issuer(full_text)
            statement_date = self.extract_statement_date(full_text)
            cashback_details = self.extract_cashback_details(pdf_path)
            line_transactions = self._extract_from_lines(full_text, card_issuer, seen)
            transactions.extend(line_transactions)
        
        transactions.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        seen_final = set()
        unique_transactions = []
        
        for t in transactions:
            desc_clean = t['description'].replace(' DEPT STORES', '').replace(' RESTAURANTS', '').replace(' JEWELLERY', '').strip()
            
            if len(desc_clean) < 2:
                continue
            
            key = f"{t['date']}_{desc_clean[:30]}_{t['amount']}_{t.get('transaction_type', 'DR')}"
            
            if key not in seen_final:
                seen_final.add(key)
                t['statement_date'] = statement_date
                t['pdf_cashback_earned'] = cashback_details.get('cashback_earned', 0.0)
                t['pdf_cashback_credited'] = cashback_details.get('cashback_credited', 0.0)
                
                if 'ADDITIONAL CASH BACK' in t.get('description', '').upper():
                    t['amount'] = -abs(t['amount'])
                
                unique_transactions.append(t)
        
        unique_transactions.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        return unique_transactions
    
    def extract_statement_date(self, text: str) -> Optional[str]:
        lines = text.split('\n')
        for i, line in enumerate(lines):
            line_upper = line.upper()
            if 'STATEMENT GENERATION DATE' in line_upper:
                for j in range(i+1, min(i+3, len(lines))):
                    next_line = lines[j].strip()
                    dates = re.findall(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', next_line)
                    if dates:
                        last_date = dates[-1]
                        parsed = self._parse_date(last_date)
                        if parsed:
                            return parsed.strftime('%d/%m/%Y')
        
        text_clean = text.replace('\n', ' ').replace('\r', ' ')
        for pattern in STATEMENT_DATE_PATTERNS:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                parsed = self._parse_date(date_str)
                if parsed:
                    return parsed.strftime('%d/%m/%Y')
        
        return None
    
    def _parse_table_row(self, row) -> Optional[Dict[str, Any]]:
        try:
            cells = [str(cell).strip() if cell else '' for cell in row]
            cells = [c for c in cells if c and len(c) > 1]
            
            if len(cells) < 2:
                return None
            
            date = None
            description = None
            merchant_category = None
            amount = None
            trans_type = 'DR'
            
            row_text = ' '.join(cells).upper()
            
            has_date = any(self._is_date(cell) for cell in cells)
            if not has_date:
                return None
            
            for cell in cells:
                if self._is_date(cell):
                    date = cell
                    break
            
            for cell in cells:
                cell_upper = cell.upper()
                if cell_upper.endswith('DR') or cell_upper.endswith('CR'):
                    try:
                        amt_clean = cell.replace(',', '').replace('Dr', '').replace('Cr', '').replace('DR', '').replace('CR', '').strip()
                        amount = float(amt_clean)
                        trans_type = 'CR' if cell_upper.endswith('CR') else 'DR'
                        break
                    except:
                        pass
            
            if amount is None:
                for cell in cells:
                    if self._is_amount(cell) and cell != date:
                        amount = self._parse_amount(cell)
                        break
            
            category_keywords = ['RESTAURANTS', 'DEPT STORES', 'JEWELLERY', 'GROCERY', 'FUEL', 'TRAVEL', 'AIRLINES', 'HOTELS', 
                              'ONLINE', 'SHOPPING', 'ENTERTAINMENT', 'UTILITIES', 'PHARMACY', 'EDUCATION']
            for kw in category_keywords:
                for cell in cells:
                    if kw in cell.upper():
                        merchant_category = cell.upper()
                        break
            
            for cell in cells:
                if cell != date and cell != merchant_category and not (cell.replace(',', '').replace('Dr', '').replace('Cr', '').strip().replace('.', '').isdigit() if cell.replace(',', '').replace('Dr', '').replace('Cr', '').strip() else False):
                    if not any(kw in cell.upper() for kw in category_keywords):
                        if self._is_date(cell):
                            continue
                        description = cell
                        break
            
            if date and amount is not None:
                parsed_date = self._parse_date(date)
                if parsed_date:
                    return {
                        'date': parsed_date.strftime('%Y-%m-%d'),
                        'description': description or 'N/A',
                        'amount': amount,
                        'merchant_category': merchant_category or 'N/A',
                        'transaction_type': trans_type,
                        'card_issuer': 'Unknown',
                        'source': 'pdf_table'
                    }
        except:
            pass
        return None
    
    def _is_date(self, text: str) -> bool:
        patterns = [
            r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$',
            r'^\d{1,2}[/-]\d{1,2}[/-]\d{2}$',
        ]
        for pattern in patterns:
            if re.match(pattern, text.strip()):
                return True
        return False
    
    def _is_amount(self, text: str) -> bool:
        cleaned = text.replace('₹', '').replace('$', '').replace(',', '').replace(' ', '').strip()
        try:
            val = float(cleaned)
            return val > 0
        except:
            return False
    
    def _parse_amount(self, amount_str: str) -> float:
        try:
            cleaned = amount_str.replace('₹', '').replace('$', '').replace(',', '').replace(' ', '').strip()
            return float(cleaned)
        except:
            return 0.0
    
    def _extract_from_lines(self, text: str, card_issuer: str, seen: set) -> List[Dict[str, Any]]:
        transactions = []
        
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 15:
                continue
            
            line_upper = line.upper()
            line_lower = line.lower()
            
            if any(kw in line_lower for kw in SKIP_KEYWORDS):
                continue
            
            if line_lower.startswith('for ') or line_lower.startswith('make ') or line_lower.startswith('if a'):
                continue
            
            trans_type = 'DR'
            cr_match = re.search(r'(\d[\d,]+\.\d{2})\s+(Cr|CR)$', line)
            if cr_match:
                trans_type = 'CR'
            
            date_match = DATE_PATTERN.match(line)
            if not date_match:
                continue
            
            date_str = date_match.group(1)
            parsed_date = self._parse_date(date_str)
            if not parsed_date:
                continue
            
            amount_match = AMOUNT_PATTERN.search(line)
            
            if not amount_match:
                continue
            
            amount_str = amount_match.group(1)
            amount = float(amount_str.replace(',', ''))
            
            if amount_match.lastindex and amount_match.group(2):
                trans_type = 'CR' if amount_match.group(2).upper() == 'CR' else 'DR'
            
            if amount > 50000 and trans_type == 'DR':
                continue
            
            desc_start = date_match.end()
            desc_end = amount_match.start()
            description = line[desc_start:desc_end].strip()
            description = re.sub(r'^[.,:\-\s]+', '', description)
            description = re.sub(r'[.,:\-\s]+$', '', description)
            
            if len(description) < 2:
                continue
            
            if amount < 10 and trans_type == 'DR':
                continue
            
            merchant_category = 'N/A'
            for kw in CATEGORY_KEYWORDS:
                if kw in line_upper:
                    merchant_category = kw
                    break
            
            key = f"{parsed_date.strftime('%d/%m/%Y')}_{description[:30]}_{amount}"
            if key not in seen:
                seen.add(key)
                transactions.append({
                    'date': parsed_date.strftime('%d/%m/%Y'),
                    'description': description[:100],
                    'amount': amount,
                    'merchant_category': merchant_category,
                    'transaction_type': trans_type,
                    'card_issuer': card_issuer,
                    'source': 'pdf_line'
                })
        
        return transactions
    
    def _parse_date(self, date_str: str):
        formats = [
            '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
            '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',
            '%m/%d/%Y', '%m/%d/%y',
        ]
        date_str = date_str.strip()
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.year < 100:
                    dt = dt.replace(year=2000 + dt.year)
                if dt.year < 1990 or dt.year > 2100:
                    day, month, year = date_str.split('/')[0], date_str.split('/')[1], date_str.split('/')[2]
                    if int(year) < 50:
                        year = '20' + year
                    else:
                        year = '19' + year
                    try:
                        return datetime(int(year), int(month), int(day))
                    except:
                        pass
                return dt
            except:
                continue
        return None
    
    def extract_cashback_details(self, pdf_path: str) -> Dict[str, Any]:
        cashback_details = {
            'cashback_earned': 0.0,
            'cashback_credited': 0.0,
            'statement_date': None
        }
        
        with self._open_pdf(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            cashback_details['statement_date'] = self.extract_statement_date(full_text)
            
            lines = full_text.split('\n')
            for i, line in enumerate(lines):
                if 'CASHBACK DETAILS' in line.upper():
                    for j in range(i+1, min(i+4, len(lines))):
                        values_line = lines[j].strip()
                        amounts = re.findall(r'([\d,]+\.?\d*)', values_line)
                        if len(amounts) >= 2:
                            try:
                                cashback_details['cashback_earned'] = float(amounts[0].replace(',', ''))
                                cashback_details['cashback_credited'] = float(amounts[1].replace(',', ''))
                            except:
                                pass
                            break
                    break
        
        return cashback_details
    
    def extract_cashback_from_pdf(self, pdf_path: str) -> Dict[str, Any]:
        cashback_info = {
            'total_cashback': 0.0,
            'cashback_rate': 0.0,
            'category_cashback': [],
            'raw_text': ''
        }
        
        with self._open_pdf(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    cashback_info['raw_text'] += text + "\n"
        
        total_patterns = [
            r'total\s*cashback[:\s]*[₹$Rs\.?\s]*([\d,]+\.?\d*)',
            r'cashback\s*earned[:\s]*[₹$Rs\.?\s]*([\d,]+\.?\d*)',
            r'total\s*reward[:\s]*[₹$Rs\.?\s]*([\d,]+\.?\d*)',
            r'your\s*reward[:\s]*[₹$Rs\.?\s]*([\d,]+\.?\d*)',
            r'cashback[:\s]*[₹$Rs\.?\s]*([\d,]+\.?\d*)',
        ]
        
        for pattern in total_patterns:
            match = re.search(pattern, cashback_info['raw_text'], re.IGNORECASE)
            if match:
                try:
                    cashback_info['total_cashback'] = float(match.group(1).replace(',', ''))
                    break
                except:
                    pass
        
        return cashback_info
