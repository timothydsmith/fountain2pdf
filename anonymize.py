"""
fountain2pdf.anonymize
------------------------
Strips contact-related fields from a parsed Fountain title page, for
producing a blind-submission copy of a script.

Scope: this only touches title-page metadata (Contact:, Email:, Phone:,
Address:, etc). It does not scan the body of the script for contact
details written inline - if a phone number or email address is typed into
the dialogue or action text itself, it will not be removed.
"""

# Any title-page key containing one of these substrings is treated as
# contact information and dropped. Matching is case-insensitive and
# substring-based so "Contact", "Email Address", "Mobile Phone" etc. are
# all caught without needing to enumerate every possible key.

CONTACT_KEY_MARKERS = (
    "contact",
    "email",
    "e-mail",
    "phone",
    "mobile",
    "tel",
    "address",
    "credit",
    "author"
)


def anonymize_title_page(title_page):
    """Return (cleaned_title_page, removed_keys)."""
    removed = []
    cleaned = {}
    for key, value in title_page.items():
        if any(marker in key.lower() for marker in CONTACT_KEY_MARKERS):
            removed.append(key)
            continue
        cleaned[key] = value
    return cleaned, removed
