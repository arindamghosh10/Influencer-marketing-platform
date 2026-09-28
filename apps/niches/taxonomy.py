"""Launch taxonomy: top-level categories, sub-niches and matching keywords.

Keywords drive the rule-based niche mapping and creator content matching. Loaded by the
`load_niches` management command (idempotent, safe to re-run after edits).
"""

TAXONOMY = [
    (
        "beauty",
        "Beauty",
        ["beauty", "makeup", "cosmetic"],
        [
            ("makeup", "Makeup", ["makeup", "lipstick", "foundation", "kajal", "eyeliner", "mascara"]),
            ("haircare", "Haircare", ["hair", "shampoo", "conditioner", "hair oil", "hairfall"]),
            ("fragrance", "Fragrance", ["perfume", "fragrance", "deodorant", "attar"]),
            ("nails", "Nails", ["nail", "manicure", "nail polish"]),
        ],
    ),
    (
        "skincare",
        "Skincare",
        ["skincare", "skin"],
        [
            ("acne-care", "Acne care", ["acne", "pimple", "salicylic", "breakout"]),
            ("anti-ageing", "Anti-ageing", ["anti-ageing", "anti-aging", "retinol", "wrinkle"]),
            ("sun-care", "Sun care", ["sunscreen", "spf", "sunblock"]),
            ("mens-grooming", "Men's grooming", ["beard", "shaving", "men's grooming", "trimmer"]),
            ("natural-skincare", "Natural / ayurvedic", ["ayurvedic", "herbal", "natural", "organic"]),
        ],
    ),
    (
        "fashion",
        "Fashion",
        ["fashion", "outfit", "style", "clothing"],
        [
            ("womens-fashion", "Women's fashion", ["kurti", "saree", "dress", "lehenga", "women's"]),
            ("mens-fashion", "Men's fashion", ["shirt", "men's", "kurta", "trousers"]),
            ("ethnic-wear", "Ethnic wear", ["ethnic", "saree", "kurta", "lehenga", "sherwani"]),
            ("streetwear", "Streetwear", ["streetwear", "sneakers", "hoodie", "oversized"]),
            ("accessories", "Jewellery & accessories", ["jewellery", "jewelry", "earrings", "watch", "bag"]),
            ("footwear", "Footwear", ["shoes", "sneakers", "footwear", "sandals", "heels"]),
        ],
    ),
    (
        "fitness",
        "Fitness",
        ["fitness", "workout", "gym", "exercise"],
        [
            ("gym", "Gym & strength", ["gym", "strength", "bodybuilding", "protein", "muscle"]),
            ("yoga", "Yoga", ["yoga", "asana", "meditation", "pranayam"]),
            ("running", "Running & cardio", ["running", "marathon", "cardio", "cycling"]),
            ("home-workouts", "Home workouts", ["home workout", "hiit", "resistance band"]),
        ],
    ),
    (
        "health-wellness",
        "Health & wellness",
        ["health", "wellness", "healthy"],
        [
            ("nutrition", "Nutrition & diet", ["nutrition", "diet", "calorie", "healthy eating"]),
            ("mental-health", "Mental health", ["mental health", "anxiety", "mindfulness", "therapy"]),
            ("womens-health", "Women's health", ["pcos", "period", "menstrual", "pregnancy"]),
        ],
    ),
    (
        "food",
        "Food",
        ["food", "recipe", "cooking", "eat"],
        [
            ("home-cooking", "Home cooking & recipes", ["recipe", "cooking", "homemade", "kitchen"]),
            (
                "food-reviews",
                "Food reviews & street food",
                ["street food", "food review", "restaurant", "cafe"],
            ),
            ("healthy-food", "Healthy food", ["healthy", "millet", "salad", "protein snack"]),
            ("baking", "Baking & desserts", ["baking", "cake", "dessert", "cookies"]),
            ("beverages", "Beverages", ["coffee", "tea", "chai", "juice", "drink"]),
        ],
    ),
    (
        "travel",
        "Travel",
        ["travel", "trip", "vacation", "explore"],
        [
            ("budget-travel", "Budget travel", ["budget travel", "backpacking", "hostel"]),
            ("luxury-travel", "Luxury travel", ["luxury", "resort", "villa", "staycation"]),
            ("adventure", "Adventure & trekking", ["trek", "adventure", "hiking", "camping"]),
        ],
    ),
    (
        "tech",
        "Tech & gadgets",
        ["tech", "gadget", "smartphone", "app"],
        [
            ("smartphones", "Smartphones", ["smartphone", "phone", "android", "iphone"]),
            ("gadgets", "Gadgets & audio", ["earbuds", "headphones", "smartwatch", "gadget"]),
            ("apps-software", "Apps & software", ["app", "software", "ai tool", "productivity"]),
        ],
    ),
    (
        "gaming",
        "Gaming",
        ["gaming", "gamer", "esports"],
        [
            ("mobile-gaming", "Mobile gaming", ["bgmi", "mobile game", "free fire"]),
            ("pc-console", "PC & console", ["pc gaming", "playstation", "xbox", "steam"]),
        ],
    ),
    (
        "parenting",
        "Parenting & kids",
        ["parenting", "mom", "dad", "baby", "kids"],
        [
            ("baby-care", "Baby care", ["baby", "diaper", "newborn", "infant"]),
            ("kids-learning", "Kids & learning", ["kids", "toys", "learning", "school"]),
        ],
    ),
    (
        "finance",
        "Personal finance",
        ["finance", "money", "saving", "invest"],
        [
            ("personal-finance", "Saving & budgeting", ["budget", "saving", "credit card", "tax"]),
            ("investing", "Investing education", ["investing", "mutual fund", "stock market", "sip"]),
        ],
    ),
    (
        "education",
        "Education & careers",
        ["education", "learn", "career", "study"],
        [
            ("exam-prep", "Exam prep", ["upsc", "neet", "jee", "exam", "study tips"]),
            ("career-skills", "Careers & skills", ["career", "interview", "resume", "upskill", "coding"]),
            ("languages", "Languages", ["english speaking", "language", "spoken english"]),
        ],
    ),
    (
        "lifestyle",
        "Lifestyle",
        ["lifestyle", "daily vlog", "routine"],
        [
            ("daily-vlogs", "Daily vlogs", ["vlog", "day in my life", "routine"]),
            ("couple-family", "Couples & family", ["couple", "family", "husband", "wife"]),
            ("minimalism", "Minimalism & productivity", ["minimalism", "productivity", "organise"]),
        ],
    ),
    (
        "home-decor",
        "Home & decor",
        ["home", "decor", "interior"],
        [
            ("interiors", "Interiors & decor", ["interior", "decor", "room makeover", "furniture"]),
            ("home-appliances", "Home appliances", ["appliance", "mixer", "air fryer", "vacuum"]),
            ("gardening", "Gardening & plants", ["plants", "gardening", "balcony garden"]),
        ],
    ),
    (
        "pets",
        "Pets",
        ["pet", "dog", "cat", "puppy"],
        [
            ("dogs", "Dogs", ["dog", "puppy", "doggo"]),
            ("cats", "Cats", ["cat", "kitten"]),
        ],
    ),
    (
        "automotive",
        "Automotive",
        ["car", "bike", "automotive", "vehicle"],
        [
            ("cars", "Cars", ["car", "suv", "ev", "sedan"]),
            ("bikes", "Bikes & scooters", ["bike", "motorcycle", "scooter", "ride"]),
        ],
    ),
    (
        "entertainment",
        "Comedy & entertainment",
        ["comedy", "funny", "entertainment"],
        [
            ("comedy", "Comedy & skits", ["comedy", "skit", "funny", "meme"]),
            ("music-dance", "Music & dance", ["music", "dance", "singing", "cover"]),
            ("movies-reviews", "Movies & OTT reviews", ["movie", "ott", "series", "review"]),
        ],
    ),
    (
        "sports",
        "Sports",
        ["sports", "cricket", "football"],
        [
            ("cricket", "Cricket", ["cricket", "ipl", "batting"]),
            ("other-sports", "Other sports", ["football", "badminton", "kabaddi", "tennis"]),
        ],
    ),
    (
        "art-diy",
        "Art, craft & DIY",
        ["art", "craft", "diy", "handmade"],
        [
            ("art", "Art & illustration", ["painting", "drawing", "illustration", "art"]),
            ("diy-crafts", "DIY & crafts", ["diy", "craft", "handmade", "resin"]),
        ],
    ),
    (
        "photography",
        "Photography & creators",
        ["photography", "camera", "content creation"],
        [
            ("photo-video", "Photo & video", ["camera", "lens", "editing", "reels tips"]),
        ],
    ),
]
