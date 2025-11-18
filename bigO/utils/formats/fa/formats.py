def LOCALE_DIGITS(text):
    english = "0123456789"
    farsi = "۰۱۲۳۴۵۶۷۸۹"
    return text.translate(str.maketrans(english, farsi))
