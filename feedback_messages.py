import random

# Pools of varied positive feedback messages to avoid eBay spam detection.
# Each list is themed by product type; the generic pool is used as fallback.

_GENERIC = [
    "Exactly as described, fast dispatch and great packaging. Really happy with this purchase!",
    "Perfect transaction from start to finish. Item arrived quickly and in great condition.",
    "Brilliant seller! Item well packaged, delivered promptly. Would definitely buy again.",
    "Smooth, hassle-free purchase. Item matched the description perfectly. Highly recommended!",
    "Fast postage, excellent packaging and item exactly as described. Five stars all round.",
    "Great communication and super quick delivery. Item arrived safely. Very pleased, thank you!",
    "Item exactly as advertised, securely packed and delivered quickly. Top-notch seller!",
    "Excellent seller — honest description, quick dispatch, item arrived in perfect condition.",
    "Fantastic purchase! Speedy delivery and item is just as described. Will buy from again.",
    "No complaints whatsoever. Quick dispatch, solid packaging, item exactly as expected. A+",
    "Really impressed with the speed of delivery and how well the item was packaged. Cheers!",
    "Item arrived on time, well protected and exactly as described. Very satisfied, thank you.",
    "Great experience — fast shipping, securely wrapped and item in excellent condition.",
    "Happy buyer! Item arrived promptly, well packaged and matches the listing perfectly.",
    "Smooth transaction. Item as described, great packaging, delivered without any issues. Thanks!",
]

_POKEMON = [
    "Card arrived in perfect condition, well protected in a sleeve and top loader. Great seller!",
    "Brilliant! Card exactly as described, securely packaged in a top loader. Very happy, cheers!",
    "Card arrived safely in a sleeve and rigid mailer. Condition spot on as listed. Excellent seller!",
    "Fast dispatch, card well protected and in the condition described. Will definitely buy again!",
    "Arrived quickly and safely packaged. Card looks great — exactly what I was after. Thank you!",
    "Great Pokémon card seller! Card in perfect nick, well protected, arrived super fast. A+++",
    "Card as described, lovely condition and very well packaged. Quick delivery too. Brilliant!",
    "Exactly what I needed for my collection! Safely packaged and arrived in perfect condition.",
    "Super fast postage and card protected perfectly. Condition matches the listing. Happy days!",
    "Card arrived mint and well protected. Honest description and quick dispatch. Top seller!",
    "Lovely card, just as described. Arrived quickly and well packaged. Would buy from again!",
    "Perfect addition to my collection. Fast postage, great packaging, card in brilliant condition.",
]

_FOOTBALL = [
    "Sticker arrived in great condition, well packaged and exactly as described. Happy collector!",
    "Brilliant seller! Sticker safely packaged and delivered quickly. Exactly what I needed. Cheers!",
    "Sticker in perfect condition, securely packed and arrived fast. Great addition to my album!",
    "Exactly as listed — sticker in great nick, well protected and dispatched promptly. Excellent!",
    "Fast delivery and sticker just as described. Well packaged and in lovely condition. Thank you!",
    "Great football sticker seller. Item arrived safely and in the condition stated. Very happy!",
    "Sticker arrived quickly, well protected and in perfect condition. Filling my album nicely!",
    "Top seller! Sticker matches description, packaged well and delivered without any issues.",
    "Sticker in brilliant condition and arrived in no time. Well packaged too. Highly recommended!",
    "Really pleased — sticker exactly as described, fast dispatch and secure packaging. A+ seller!",
]


def get_feedback(item_title: str = "") -> str:
    """Return a random positive feedback message, biased by item title keywords."""
    title_lower = item_title.lower()
    if any(k in title_lower for k in ("pokemon", "pokémon", "pikachu", "charizard", "card", "tcg", "holo")):
        pool = _POKEMON + _GENERIC
    elif any(k in title_lower for k in ("sticker", "panini", "topps", "football", "soccer", "album", "swap")):
        pool = _FOOTBALL + _GENERIC
    else:
        pool = _GENERIC
    return random.choice(pool)
