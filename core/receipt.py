"""Bilingual (English / Arabic) Tawazon receipt-voucher PDF generator.

Rendered with reportlab. Arabic is shaped with arabic_reshaper + python-bidi and
drawn with the Amiri font (bundled in core/static/fonts). Falls back gracefully
if the Arabic libraries/fonts are unavailable.
"""
import io
import os
from django.conf import settings

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# ── palette ──────────────────────────────────────────────────────────────
ACCENT   = colors.HexColor('#1e3a8a')   # deep navy blue (different from the green)
ACCENT_D = colors.HexColor('#172a63')
INK      = colors.HexColor('#0f172a')
MUTED    = colors.HexColor('#64748b')
BOX      = colors.HexColor('#475569')   # darker box borders (clearly visible)
BOX_FILL = colors.HexColor('#f8fafc')

WEBSITE_URL = 'http://tawazonoman.com/'
WEBSITE_LABEL = 'tawazonoman.com'
VAT_NO = 'OM1100300426'


def receipt_verify_token(payment):
    """Short unforgeable code tied to this payment (HMAC over the server's
    SECRET_KEY). Printed on the receipt and embedded in the verification QR —
    it lets anyone confirm the authentic amounts against the database, so a
    PDF edited afterwards can be detected."""
    import hmac, hashlib
    msg = f'receipt:{payment.pk}:{payment.payment_id}'.encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()
    return digest[:10].upper()

_qr_cache = {}


def _website_qr_png(url):
    """A fresh BytesIO PNG QR code that scans straight to `url`. The encoded
    bytes are cached per URL (for the process lifetime) so repeat receipts
    don't regenerate the QR matrix; each call still returns a new stream."""
    raw = _qr_cache.get(url)
    if raw is None:
        import qrcode
        img = qrcode.make(url, border=1)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        raw = buf.getvalue()
        _qr_cache[url] = raw
    return io.BytesIO(raw)
LINE     = colors.HexColor('#cbd5e1')

FONTS_DIR = os.path.join(settings.BASE_DIR, 'core', 'static', 'fonts')

# ── font registration (once) ─────────────────────────────────────────────
_AR = 'Amiri'
_AR_B = 'Amiri-Bold'
_HAS_AR = False


def _register_fonts():
    global _HAS_AR
    try:
        if 'Amiri' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(_AR, os.path.join(FONTS_DIR, 'Amiri-Regular.ttf')))
            pdfmetrics.registerFont(TTFont(_AR_B, os.path.join(FONTS_DIR, 'Amiri-Bold.ttf')))
        _HAS_AR = True
    except Exception:
        _HAS_AR = False


try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def _shape(t):
        return get_display(arabic_reshaper.reshape(t))
except Exception:  # pragma: no cover
    def _shape(t):
        return t


def _ar(t):
    """Shape an Arabic string for correct connected/RTL rendering."""
    return _shape(t) if t else ''


# ── number → English words (for the amount box) ──────────────────────────
_ONES = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
         'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
         'Seventeen', 'Eighteen', 'Nineteen']
_TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']


def _three(n):
    out = ''
    if n >= 100:
        out += _ONES[n // 100] + ' Hundred'
        n %= 100
        if n:
            out += ' '
    if n >= 20:
        out += _TENS[n // 10]
        if n % 10:
            out += ' ' + _ONES[n % 10]
    elif n:
        out += _ONES[n]
    return out


def _num_words(n):
    n = int(n)
    if n == 0:
        return 'Zero'
    parts, scale = [], ['', ' Thousand', ' Million', ' Billion']
    i = 0
    while n > 0 and i < len(scale):
        chunk = n % 1000
        if chunk:
            parts.append(_three(chunk) + scale[i])
        n //= 1000
        i += 1
    return ' '.join(reversed(parts))


# ── drawing helpers ──────────────────────────────────────────────────────
def build_payment_receipt(payment, verify_url=None):
    _register_fonts()
    case = payment.case
    client = case.client
    debtor = case.debtor

    # Amounts in OMR
    def _to_omr(amount, currency):
        if amount is None:
            return None
        r = float(currency.value) if currency and currency.value else 1
        return float(amount) / r if r else float(amount)

    amt = _to_omr(payment.amount, payment.collection_currency) or 0.0
    rials = int(amt)
    baisa = int(round((amt - rials) * 1000))
    if baisa == 1000:
        rials += 1
        baisa = 0
    words = _num_words(rials) + ' Rials'
    if baisa:
        words += f' and {_num_words(baisa)} Baisa'
    words += ' Only'

    method = (payment.payment_method or '').lower()
    mode_name = payment.payment_mode.name if payment.payment_mode else ''
    is_cheque = 'che' in method or 'check' in method or 'che' in mode_name.lower()
    is_cash = 'cash' in method or 'cash' in mode_name.lower()

    buf = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buf, pagesize=A4)
    L, R = 40, W - 40
    cw = R - L

    # Latin (built-in) + Arabic (Amiri) font names
    LAT = 'Helvetica'
    LAT_B = 'Helvetica-Bold'
    ARF = _AR_B if _HAS_AR else LAT_B
    ARR = _AR if _HAS_AR else LAT

    def T(x, y, s, f=LAT, sz=9, col=INK):
        c.setFont(f, sz); c.setFillColor(col); c.drawString(x, y, s)

    def TR(x, y, s, f=LAT, sz=9, col=INK):
        c.setFont(f, sz); c.setFillColor(col); c.drawRightString(x, y, s)

    def TC(x, y, s, f=LAT, sz=9, col=INK):
        c.setFont(f, sz); c.setFillColor(col); c.drawCentredString(x, y, s)

    def AR(x, y, s, sz=10, col=INK, bold=True):
        c.setFont(ARF if bold else ARR, sz); c.setFillColor(col); c.drawRightString(x, y, _ar(s))

    def box(x, y, w, h, stroke=BOX, fill=None, lw=1):
        if fill:
            c.setFillColor(fill); c.rect(x, y, w, h, stroke=0, fill=1)
        c.setStrokeColor(stroke); c.setLineWidth(lw); c.rect(x, y, w, h, stroke=1, fill=0)

    # ── HEADER ──
    y = H - 46
    # small logo (left)
    try:
        img = ImageReader(os.path.join(settings.BASE_DIR, 'logo.png'))
        iw, ih = img.getSize()
        lw = 118.0
        lh = lw * ih / iw
        c.drawImage(img, L, y - lh + 8, width=lw, height=lh, mask='auto')
    except Exception:
        T(L, y, 'TAWAZON', LAT_B, 18, ACCENT)
    # title (right)
    AR(R, y - 2, 'سند قبض', sz=26, col=ACCENT, bold=True)
    c.setFont(LAT_B, 9.5); c.setFillColor(MUTED)
    c.drawRightString(R, y - 20, 'R E C E I P T   V O U C H E R')

    c.setStrokeColor(ACCENT); c.setLineWidth(2)
    yd = y - 34
    c.line(L, yd, R, yd)

    gap = 14

    def lbox(x, top, w, h, en, arb, val, vf=LAT_B, vs=10):
        """A labelled field: EN label (left) + AR label (right) above a bordered box."""
        T(x, top + 5, en, LAT_B, 7.5, MUTED)
        AR(x + w, top + 5, arb, sz=9.5, col=ACCENT)
        box(x, top - h, w, h, fill=BOX_FILL)
        c.setFont(vf, vs); c.setFillColor(INK)
        c.drawString(x + 8, top - h + (h - vs) / 2 + 1, str(val))

    # ── top 3 boxes: Receipt No / Date / VAT No ──
    cur = yd - 30
    bh = 28
    bw3 = (cw - 2 * gap) / 3
    lbox(L, cur, bw3, bh, 'RECEIPT NO.', 'رقم الإيصال', payment.receipt_no or '')
    lbox(L + bw3 + gap, cur, bw3, bh, 'DATE', 'التاريخ',
         payment.payment_date.strftime('%d-%m-%Y') if payment.payment_date else '')
    lbox(L + 2 * (bw3 + gap), cur, bw3, bh, 'VAT NO.', 'الرقم الضريبي', VAT_NO)
    cur -= bh + 32

    # ── NEW FIELDS: Client / Client Ref / Debtor / Tawazon Ref (2×2) ──
    fbw = (cw - gap) / 2
    fh = 28
    lbox(L, cur, fbw, fh, 'CLIENT NAME', 'اسم العميل', client.name if client else '')
    lbox(L + fbw + gap, cur, fbw, fh, 'CLIENT REFERENCE NO.', 'الرقم المرجعي للعميل',
         case.account_no or '')
    cur -= fh + 28
    lbox(L, cur, fbw, fh, 'DEBTOR NAME', 'اسم المدين', debtor.name if debtor else '')
    lbox(L + fbw + gap, cur, fbw, fh, 'TAWAZON REFERENCE NO.', 'الرقم المرجعي لتوازن', case.case_id or '')
    cur -= fh + 34

    # ── Received with thanks from ──
    T(L, cur + 5, 'RECEIVED WITH THANKS FROM MR. / M/S', LAT_B, 8, MUTED)
    AR(R, cur + 5, 'استلمنا من الفاضل / الأفاضل', sz=11, col=ACCENT)
    box(L, cur - 24, cw, 22, fill=BOX_FILL)
    T(L + 8, cur - 24 + 6.5, debtor.name if debtor else '', LAT_B, 11, INK)
    cur -= 24 + 36

    # ── Amount box (sum in rials) ──
    hh, vh = 20, 28
    rcol, bcol = 80, 62
    lcol = cw - rcol - bcol
    top = cur
    c.setFillColor(ACCENT); c.rect(L, top - hh, lcol, hh, stroke=0, fill=1)
    c.setFillColor(ACCENT); c.rect(L + lcol, top - hh, rcol, hh, stroke=0, fill=1)
    c.setFillColor(ACCENT_D); c.rect(L + lcol + rcol, top - hh, bcol, hh, stroke=0, fill=1)
    T(L + 8, top - hh + 6.5, 'THE SUM OF RIALS OMANI', LAT_B, 8, colors.white)
    AR(L + lcol - 8, top - hh + 6.5, 'مبلغ وقدره ريال عماني', sz=10, col=colors.white)
    TC(L + lcol + rcol / 2, top - hh + 6.5, 'R.O. ' + _ar('ريال'), ARF, 9.5, colors.white)
    TC(L + lcol + rcol + bcol / 2, top - hh + 6.5, 'Bz. ' + _ar('بيسة'), ARF, 9.5, colors.white)
    vy = top - hh - vh
    box(L, vy, lcol, vh); box(L + lcol, vy, rcol, vh); box(L + lcol + rcol, vy, bcol, vh)

    # ── tamper-evident security background inside the amount boxes ──
    # Fine diagonal lines + micro-printed authentic figures behind the digits:
    # covering a number with a white box visibly breaks the pattern, and the
    # 3pt micro-text cannot be convincingly retyped by hand.
    _amt_str = f'OMR {rials}.{baisa:03d}'
    try:
        c.saveState()
        pth = c.beginPath(); pth.rect(L + 0.7, vy + 0.7, cw - 1.4, vh - 1.4)
        c.clipPath(pth, stroke=0, fill=0)
        c.setStrokeColor(ACCENT); c.setStrokeAlpha(0.10); c.setLineWidth(0.4)
        xx = L - vh
        while xx < R:
            c.line(xx, vy, xx + vh, vy + vh)
            xx += 5
        c.setFillColor(ACCENT); c.setFillAlpha(0.20)
        c.setFont(LAT_B, 3.1)
        micro = f'{payment.receipt_no} • {_amt_str} • ' * 30
        for yy in (vy + 2.5, vy + vh / 2 - 1.5, vy + vh - 5.5):
            c.drawString(L + 2, yy, micro[:400])
        c.restoreState()
    except Exception:
        try:
            c.restoreState()
        except Exception:
            pass

    c.setFont(LAT_B, 9); c.setFillColor(INK)
    c.drawString(L + 8, vy + vh / 2 - 3, words)
    TC(L + lcol + rcol / 2, vy + vh / 2 - 4, f'{rials:,}', LAT_B, 12, ACCENT)
    TC(L + lcol + rcol + bcol / 2, vy + vh / 2 - 4, f'{baisa:03d}', LAT_B, 12, ACCENT)

    # Micro-print strip under the amount block repeating the authentic figures.
    c.setFillColor(MUTED); c.setFont(LAT_B, 3.2)
    _code = receipt_verify_token(payment)
    strip = f'AUTHENTIC • {payment.receipt_no} • {_amt_str} • CODE {_code[:5]}-{_code[5:]} • ' * 12
    from reportlab.pdfbase.pdfmetrics import stringWidth as _sw
    while strip and _sw(strip, LAT_B, 3.2) > cw:
        strip = strip[:-10]
    c.drawString(L, vy - 5.5, strip)
    cur = vy - 32

    # ── Cash / Cheque row ──
    def _check(x, cy, on):
        box(x, cy, 11, 11, stroke=BOX, lw=1.2)
        if on:
            c.setStrokeColor(ACCENT); c.setLineWidth(1.8)
            c.line(x + 2, cy + 5, x + 4.5, cy + 2.5); c.line(x + 4.5, cy + 2.5, x + 9, cy + 8.5)
    py = cur
    _check(L, py, is_cash)
    T(L + 16, py + 1.5, 'Cash', LAT_B, 9, INK); AR(L + 64, py + 1.5, 'نقداً', sz=10)
    _check(L + 96, py, is_cheque)
    T(L + 112, py + 1.5, 'Cheque', LAT_B, 9, INK); AR(L + 168, py + 1.5, 'شيك', sz=10)
    T(L + 188, py + 1.5, 'Cheque No.', LAT_B, 8, MUTED)
    T(L + 248, py + 1.5, payment.cheque_number or '', LAT, 9, INK)
    AR(R, py + 1.5, 'رقم الشيك', sz=10, col=ACCENT)
    c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(L + 248, py - 2, R - 70, py - 2)
    cur -= 30

    # ── Being / For ──
    being = payment.notes.strip() if payment.notes else f'Collection towards case {case.case_id}'
    T(L, cur + 5, 'BEING / FOR', LAT_B, 8, MUTED)
    AR(R, cur + 5, 'وذلك عن', sz=11, col=ACCENT)
    box(L, cur - 30, cw, 28, fill=BOX_FILL)
    T(L + 8, cur - 30 + 9, being[:110], LAT, 10, INK)
    cur -= 30 + 44

    # ── Signatures ──
    sy = cur
    colw = (cw - 30) / 2
    T(L, sy, "RECEIVER'S SIGNATURE", LAT_B, 8, MUTED)
    AR(L + colw, sy, 'توقيع المستلم', sz=10, col=ACCENT)
    c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(L, sy - 24, L + colw, sy - 24)
    T(L, sy - 36, 'NAME', LAT_B, 8, MUTED)
    AR(L + colw, sy - 36, 'الاسم', sz=10, col=ACCENT)
    c.line(L, sy - 52, L + colw, sy - 52)

    sx = L + colw + 30
    T(sx, sy, 'FOR TAWAZON — SIGNATURE & STAMP', LAT_B, 7.5, MUTED)
    AR(R, sy - 12, 'عن توازن — التوقيع والختم', sz=9.5, col=ACCENT)
    c.setStrokeColor(LINE); c.line(sx, sy - 44, R, sy - 44)
    T(sx, sy - 56, 'PHONE', LAT_B, 8, MUTED)
    AR(R, sy - 56, 'الهاتف', sz=10, col=ACCENT)

    # ── Footer ──
    c.setStrokeColor(ACCENT); c.setLineWidth(1.4); c.line(L, 66, R, 66)
    T(L, 50, 'OFFICE', LAT_B, 8, ACCENT)
    T(L, 38, 'Muscat, Sultanate of Oman', LAT, 8.5, INK)
    T(L, 27, 'Visiting address by appointment', LAT, 7.5, MUTED)
    T(L + 165, 50, 'PHONE', LAT_B, 8, ACCENT)
    T(L + 165, 38, '+968 9236 3536', LAT, 8.5, INK)
    T(L + 300, 50, 'EMAIL', LAT_B, 8, ACCENT)
    T(L + 300, 38, 'info@tawazonoman.com', LAT, 8.5, INK)

    # QR code (bottom-right) — scans straight to the Tawazon website.
    try:
        qr_img = ImageReader(_website_qr_png(WEBSITE_URL))
        qs = 42
        qx, qy = R - qs, 18
        c.drawImage(qr_img, qx, qy, width=qs, height=qs, mask='auto')
        TC(qx + qs / 2, qy - 9, WEBSITE_LABEL, LAT, 6.5, MUTED)
    except Exception:
        pass

    # Verification code (footer) — entered at <site>/receipt/verify/ it shows
    # the authentic figures straight from the database, so a tampered PDF can
    # be spotted immediately.
    if verify_url:
        code = receipt_verify_token(payment)
        # host part of the verify URL, e.g. "tawazonoman.com"
        host = verify_url.split('//', 1)[-1].split('/', 1)[0]
        T(L, 13, 'VERIFICATION CODE ', LAT_B, 7.5, ACCENT)
        from reportlab.pdfbase.pdfmetrics import stringWidth as _sw2
        _cx = L + _sw2('VERIFICATION CODE ', LAT_B, 7.5)
        T(_cx, 13, f'{code[:5]}-{code[5:]}', LAT_B, 8, INK)
        _cx += _sw2(f'{code[:5]}-{code[5:]}', LAT_B, 8)
        T(_cx + 6, 13, f'— verify this receipt at {host}/receipt/verify/', LAT, 7, MUTED)

    c.showPage()
    c.save()
    pdf = buf.getvalue()
    buf.close()
    return pdf
