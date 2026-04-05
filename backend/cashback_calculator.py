from typing import List, Dict, Any, Optional
from datetime import datetime


class CashbackCalculator:
    CATEGORY_CASHBACK_RATES = {
        'grocery': 0.10,
        'dining': 0.10,
        'utilities': 0.10,
        'airtel': 0.25,
        'gems': 0.00,
        'jewelry': 0.01,
        'travel': 0.01,
        'fuel': 0.01,
        'entertainment': 0.01,
        'shopping': 0.01,
        'default': 0.01
    }
    
    def __init__(self, custom_rates: Optional[Dict[str, float]] = None):
        if custom_rates is not None:
            self.CATEGORY_CASHBACK_RATES.update(custom_rates)
    
    def categorize_transaction(self, description: str, merchant_category: str = 'N/A') -> str:
        if not description:
            return 'default'
        
        desc_lower = description.lower()
        
        if 'airtel' in desc_lower:
            return 'airtel'
        
        if 'gems' in desc_lower:
            return 'gems'
        
        if 'jewel' in desc_lower or 'jewellery' in desc_lower:
            return 'jewelry'
        
        if 'avenue e commerce' in desc_lower:
            return 'travel'
        
        if 'bigbasket' in desc_lower or 'grocery' in desc_lower or 'supermarket' in desc_lower:
            return 'grocery'
        if 'zomato' in desc_lower or 'swiggy' in desc_lower or 'restaurant' in desc_lower or 'food' in desc_lower:
            return 'dining'
        if 'jewel' in desc_lower or 'jewellery' in desc_lower:
            return 'jewelry'
        if 'taxi' in desc_lower or 'uber' in desc_lower or 'ola' in desc_lower:
            return 'travel'
        if 'fuel' in desc_lower or 'petrol' in desc_lower or 'gas' in desc_lower:
            return 'fuel'
        if 'utility' in desc_lower or 'utilities' in desc_lower or 'bill' in desc_lower or 'airtel' in desc_lower or 'jio' in desc_lower or 'bsnl' in desc_lower or 'electricity' in desc_lower or 'water bill' in desc_lower or 'gas bill' in desc_lower:
            return 'utilities'
        
        cat_upper = merchant_category.upper() if merchant_category else ''
        if 'RESTAURANT' in cat_upper:
            return 'dining'
        if 'GROCERY' in cat_upper:
            return 'grocery'
        if 'DEPT' in cat_upper:
            return 'grocery'
        if 'UTIL' in cat_upper:
            return 'utilities'
        if 'JEWEL' in cat_upper:
            return 'jewelry'
        if 'FUEL' in cat_upper:
            return 'fuel'
        if 'TRAVEL' in cat_upper or 'AIRLINE' in cat_upper or 'HOTEL' in cat_upper:
            return 'travel'
        if 'ENTERTAINMENT' in cat_upper or 'MOVIE' in cat_upper:
            return 'entertainment'
        if 'SHOPPING' in cat_upper or 'ONLINE' in cat_upper:
            return 'shopping'
        
        return 'default'
    
    def get_cashback_rate(self, category: str) -> float:
        return self.CATEGORY_CASHBACK_RATES.get(category, self.CATEGORY_CASHBACK_RATES['default'])
    
    def calculate_cashback(self, amount: float, category: str) -> float:
        rate = self.get_cashback_rate(category)
        return round(amount * rate, 2)
    
    def calculate_total_cashback(self, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = {
            'total_transactions': len(transactions),
            'total_spend': 0.0,
            'total_cashback': 0.0,
            'dr_transactions': 0,
            'cr_transactions': 0,
            'by_category': {},
            'by_issuer': {},
            'by_month': {},
            'transactions': []
        }
        
        for trans in transactions:
            trans_type = trans.get('transaction_type', 'DR')
            merchant_category = trans.get('merchant_category', 'N/A')
            
            if trans_type == 'CR':
                trans['bank_category'] = 'Credit'
                trans['cashback_category'] = 'N/A'
                trans['cashback_rate'] = 0
                trans['calculated_cashback'] = 0.0
                results['cr_transactions'] += 1
                results['transactions'].append(trans)
                continue
            
            amount = abs(trans.get('amount', 0))
            category = self.categorize_transaction(trans.get('description', ''), merchant_category)
            rate = self.get_cashback_rate(category)
            cashback = self.calculate_cashback(amount, category)
            
            trans['bank_category'] = merchant_category
            trans['cashback_category'] = category
            trans['cashback_rate'] = rate
            trans['calculated_cashback'] = cashback
            trans['is_capped'] = False
            
            results['total_spend'] += amount
            results['total_cashback'] += cashback
            results['dr_transactions'] += 1
            results['transactions'].append(trans)
            
            if category not in results['by_category']:
                results['by_category'][category] = {'spend': 0.0, 'cashback': 0.0, 'count': 0, 'rate': rate}
            results['by_category'][category]['spend'] += amount
            results['by_category'][category]['cashback'] += cashback
            results['by_category'][category]['count'] += 1
            
            issuer = trans.get('card_issuer', 'Unknown')
            if issuer not in results['by_issuer']:
                results['by_issuer'][issuer] = {'spend': 0.0, 'cashback': 0.0, 'count': 0}
            results['by_issuer'][issuer]['spend'] += amount
            results['by_issuer'][issuer]['cashback'] += cashback
            results['by_issuer'][issuer]['count'] += 1
            
            trans_date = trans.get('date', '')
            if trans_date:
                try:
                    if '/' in trans_date:
                        dt = datetime.strptime(trans_date, '%d/%m/%Y')
                    else:
                        dt = datetime.strptime(trans_date, '%Y-%m-%d')
                    month_key = dt.strftime('%Y-%m')
                    month_display = dt.strftime('%B %Y')
                    
                    if month_key not in results['by_month']:
                        results['by_month'][month_key] = {
                            'display': month_display,
                            'spend': 0.0,
                            'cashback': 0.0,
                            'count': 0
                        }
                    results['by_month'][month_key]['spend'] += amount
                    results['by_month'][month_key]['cashback'] += cashback
                    results['by_month'][month_key]['count'] += 1
                except:
                    pass
        
        AIRTEL_MONTHLY_CAP = 250.0
        airtel_by_month = {}
        for trans in results['transactions']:
            if trans.get('cashback_category') == 'airtel':
                trans_date = trans.get('date', '')
                if trans_date:
                    try:
                        if '/' in trans_date:
                            dt = datetime.strptime(trans_date, '%d/%m/%Y')
                        else:
                            dt = datetime.strptime(trans_date, '%Y-%m-%d')
                        month_key = dt.strftime('%Y-%m')
                        if month_key not in airtel_by_month:
                            airtel_by_month[month_key] = []
                        airtel_by_month[month_key].append(trans)
                    except:
                        pass
        
        total_cashback_adjustment = 0.0
        for month_key, month_trans in airtel_by_month.items():
            total_airtel_cb = sum(t.get('calculated_cashback', 0) for t in month_trans)
            if total_airtel_cb > AIRTEL_MONTHLY_CAP:
                excess = total_airtel_cb - AIRTEL_MONTHLY_CAP
                reduction_per_trans = excess / len(month_trans)
                for trans in month_trans:
                    trans['is_capped'] = True
                    trans['original_cashback'] = trans['calculated_cashback']
                    trans['calculated_cashback'] = round(trans['calculated_cashback'] - reduction_per_trans, 2)
                    total_cashback_adjustment += reduction_per_trans
        
        results['total_cashback'] = round(results['total_cashback'] - total_cashback_adjustment, 2)
        
        results['total_spend'] = round(results['total_spend'], 2)
        
        return results
    
    def compare_cashback(self, calculated: float, stated: float, tolerance: float = 1.0) -> Dict[str, Any]:
        difference = calculated - stated
        percent_diff = (difference / stated * 100) if stated != 0 else 0
        
        return {
            'calculated': round(calculated, 2),
            'stated': round(stated, 2),
            'difference': round(difference, 2),
            'percent_difference': round(percent_diff, 2),
            'match': abs(difference) <= tolerance,
            'status': 'Match' if abs(difference) <= tolerance else 'Mismatch'
        }
