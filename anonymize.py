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
    """Return (cleaned_title_page, removed_keys).

    `title_page` is the dict[str, list[str]] produced by
    parser._parse_title_page - one entry per "Key: value" line found at
    the top of the Fountain file, keyed by the lowercased key.
    """
    removed = []
    cleaned = {}
    # .items() lets us loop over a dict's (key, value) pairs together in
    # one go, instead of looping over keys and looking each value up
    # separately.
    for key, value in title_page.items():
        # any(...) over a generator expression: "does `marker` appear
        # inside `key.lower()`, for at least one marker in
        # CONTACT_KEY_MARKERS?" - `in` on strings is a substring test, so
        # this catches e.g. "mobile phone" matching the "phone" marker,
        # not just an exact match against the whole key.
        if any(marker in key.lower() for marker in CONTACT_KEY_MARKERS):
            removed.append(key)
            # `continue` skips straight to the next loop iteration without
            # running the `cleaned[key] = value` line below - i.e. this key
            # is deliberately left out of the cleaned dict.
            continue
        cleaned[key] = value
    return cleaned, removed
