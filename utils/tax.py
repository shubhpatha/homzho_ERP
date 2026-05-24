"""
utils/tax.py - GST calculations for inclusive plan pricing.
"""

CGST_RATE = 0.09
SGST_RATE = 0.09
TOTAL_GST_RATE = CGST_RATE + SGST_RATE


def calculate_inclusive_gst(amount):
    """Return GST breakup when `amount` already includes CGST and SGST."""
    gross_amount = float(amount or 0)
    taxable_amount = gross_amount / (1 + TOTAL_GST_RATE)
    cgst_amount = taxable_amount * CGST_RATE
    sgst_amount = taxable_amount * SGST_RATE

    return {
        'gross_amount': gross_amount,
        'taxable_amount': taxable_amount,
        'cgst_amount': cgst_amount,
        'sgst_amount': sgst_amount,
        'total_tax_amount': cgst_amount + sgst_amount,
    }
