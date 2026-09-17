"""Verified official fallback destinations; no invented venue IDs.

Sources checked 2026-09-17 by the read-only recovery audit:
- Meet: active restaurant prompt + restaurants.tagme_venue_id; public widget identity.
- Frêneze: active prompt; public smartlink identity.
- Madonna: existing TAGME_WIDGET_URL; verified public redirect to its venue.
No official booking link was evidenced for Levvai: use the current DB phone.
"""
OFFICIAL_RESERVATION_URLS = {
    'meet_and_eat': 'https://reservation-widget.tagme.com.br/reservation/schedule/62ffd74ddaf31500126b3e29/reservationWidget',
    'freneze': 'https://reservation-widget.tagme.com.br/smartlink/6a73919fef73b2f5d86824de',
    'madonna_cucina': 'https://usetag.me/madonnacucina',
}
