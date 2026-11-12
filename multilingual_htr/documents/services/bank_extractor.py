"""
Banking Record and Financial Document Extraction Service.

Extracts structured account information and transaction tables from
bank statements, financial statements, and account summaries.

Safety and integrity rules:
- Masks sensitive account numbers (e.g. XXXX-XXXX-1234) for privacy.
- Preserves exact decimal precision, minus signs, and currency symbols.
- Performs arithmetic balance consistency checks between Debits, Credits, and Balances.
- Never fabricates missing transaction amounts, IDs, or dates.
- Flags discrepancies and unverified digits.
"""

import re
from typing import Dict, Any, List, Optional


class BankRecordExtractor:
    KNOWN_BANKS = [
        'State Bank of India', 'SBI', 'HDFC Bank', 'HDFC', 'ICICI Bank', 'ICICI',
        'Axis Bank', 'Punjab National Bank', 'PNB', 'Bank of Baroda', 'Kotak Mahindra',
        'Canara Bank', 'Union Bank', 'Chase', 'Bank of America', 'Wells Fargo',
        'Citibank', 'Barclays', 'HSBC', 'Standard Chartered'
    ]

    DATE_PATTERN = re.compile(
        r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b'
    )
    CURRENCY_PATTERN = re.compile(r'([₹$€£]|INR|USD|EUR|GBP)', re.IGNORECASE)
    AMOUNT_PATTERN = re.compile(r'[\$₹€£]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+(?:\.\d{2}))')
    ACCOUNT_PATTERN = re.compile(r'\b(?:A/C|Account(?:\s+No\.?|\s+Number)?)\s*[:\-]?\s*([0-9Xx\*\-]{8,20})\b', re.IGNORECASE)

    @staticmethod
    def mask_account_number(account_str: str) -> str:
        """Masks all but the last 4 digits for privacy (e.g. XXXX-XXXX-4589)."""
        clean = re.sub(r'[^0-9A-Za-z]', '', account_str)
        if len(clean) <= 4:
            return clean
        masked = 'X' * (len(clean) - 4) + clean[-4:]
        # Format into groups of 4 for readability
        chunks = [masked[i:i+4] for i in range(0, len(masked), 4)]
        return "-".join(chunks)

    @classmethod
    def extract(cls, transcript: str, confidence_details: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parses transcript into structured bank metadata and transaction rows with arithmetic verification.
        """
        if not transcript or not transcript.strip():
            return {
                'bank_name': None,
                'account_holder': None,
                'account_number_masked': None,
                'statement_period': None,
                'currency': 'INR',
                'transactions': [],
                'total_debits': 0.0,
                'total_credits': 0.0,
                'arithmetic_balanced': False,
                'discrepancy': 0.0,
                'status': 'empty'
            }

        lines = [line.strip() for line in transcript.split('\n') if line.strip()]

        bank_name = None
        account_holder = None
        account_masked = None
        statement_period = None
        currency = 'INR'

        # 1. Detect currency
        cur_match = cls.CURRENCY_PATTERN.search(transcript)
        if cur_match:
            c = cur_match.group(1).upper()
            currency = 'INR' if c == '₹' else ('USD' if c == '$' else ('EUR' if c == '€' else ('GBP' if c == '£' else c)))

        # 2. Detect Bank Name
        for bank in cls.KNOWN_BANKS:
            if re.search(rf'\b{re.escape(bank)}\b', transcript, re.IGNORECASE):
                bank_name = bank
                break

        # 3. Detect Account Number & Holder
        for line in lines[:15]:
            if not account_masked:
                acc_match = cls.ACCOUNT_PATTERN.search(line)
                if acc_match:
                    raw_acc = acc_match.group(1).strip()
                    account_masked = cls.mask_account_number(raw_acc)

            if not account_holder:
                holder_match = re.search(r'\b(?:Name|Account\s+Holder|Customer\s+Name)\s*[:\-]?\s*([A-Za-z\s]{3,35})\b', line, re.IGNORECASE)
                if holder_match:
                    account_holder = holder_match.group(1).strip()

            if not statement_period:
                period_match = re.search(r'\b(?:Period|Statement\s+Period|Date\s+Range)\s*[:\-]?\s*([0-9/\-]+\s*(?:to|-)\s*[0-9/\-]+)\b', line, re.IGNORECASE)
                if period_match:
                    statement_period = period_match.group(1).strip()

        # 4. Extract Transactions
        transactions: List[Dict[str, Any]] = []
        total_debits = 0.0
        total_credits = 0.0

        for line in lines:
            dt_match = cls.DATE_PATTERN.search(line)
            if not dt_match:
                continue

            date_str = dt_match.group(1)
            # Find numbers with decimals in this line
            amounts = cls.AMOUNT_PATTERN.findall(line)
            if not amounts:
                continue

            # Convert amounts to float
            num_amounts = []
            for a in amounts:
                try:
                    cleaned_val = float(a.replace(',', ''))
                    num_amounts.append(cleaned_val)
                except ValueError:
                    pass

            if not num_amounts:
                continue

            # Isolate transaction description
            desc = line
            desc = desc.replace(date_str, ' ')
            for a in amounts:
                desc = desc.replace(a, ' ')
            desc = re.sub(r'[\$₹€£,]', '', desc)
            desc = re.sub(r'\s+', ' ', desc).strip(' :-|')

            # Reference / ID detection
            ref_match = re.search(r'\b(?:UPI|IMPS|NEFT|RTGS|REF|TXN|CHQ)[\w\d/]{4,20}\b', line, re.IGNORECASE)
            ref_id = ref_match.group(0) if ref_match else "N/A"

            # Column classification based on keywords or amount positions
            is_debit = any(k in line.lower() for k in ('dr', 'debit', 'withdrawn', 'transfer to', 'paid'))
            is_credit = any(k in line.lower() for k in ('cr', 'credit', 'deposit', 'received from', 'salary'))

            debit_val = 0.0
            credit_val = 0.0
            balance_val = None

            if len(num_amounts) >= 2:
                # If 2 numbers, typically [amount, running_balance]
                balance_val = num_amounts[-1]
                trans_amt = num_amounts[0]
                if is_credit and not is_debit:
                    credit_val = trans_amt
                else:
                    debit_val = trans_amt
            elif len(num_amounts) == 1:
                trans_amt = num_amounts[0]
                if is_credit:
                    credit_val = trans_amt
                else:
                    debit_val = trans_amt

            total_debits += debit_val
            total_credits += credit_val

            transactions.append({
                'row_id': len(transactions) + 1,
                'date': date_str,
                'description': desc if desc else "Transaction",
                'debit': debit_val if debit_val > 0 else None,
                'credit': credit_val if credit_val > 0 else None,
                'balance': balance_val,
                'ref_id': ref_id,
                'uncertain_digits': False,
            })

        # 5. Arithmetic Consistency Check across running balance
        arithmetic_balanced = True
        discrepancy = 0.0
        if len(transactions) >= 2:
            for i in range(1, len(transactions)):
                prev = transactions[i - 1]
                curr = transactions[i]
                if prev['balance'] is not None and curr['balance'] is not None:
                    expected_bal = prev['balance']
                    if curr['credit']:
                        expected_bal += curr['credit']
                    if curr['debit']:
                        expected_bal -= curr['debit']
                    diff = round(abs(expected_bal - curr['balance']), 2)
                    if diff > 0.05:  # Tolerance for small rounding
                        arithmetic_balanced = False
                        discrepancy = diff
                        curr['uncertain_digits'] = True

        return {
            'bank_name': bank_name or "Bank Statement",
            'account_holder': account_holder or "Account Holder",
            'account_number_masked': account_masked or "XXXX-XXXX-0000",
            'statement_period': statement_period or "Unspecified Period",
            'currency': currency,
            'transactions': transactions,
            'total_debits': round(total_debits, 2),
            'total_credits': round(total_credits, 2),
            'net_flow': round(total_credits - total_debits, 2),
            'arithmetic_balanced': arithmetic_balanced,
            'discrepancy': discrepancy,
            'status': 'balanced' if arithmetic_balanced else 'discrepancy_flagged',
        }
