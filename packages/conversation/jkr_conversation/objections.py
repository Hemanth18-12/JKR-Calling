"""Structured objection-handling and conversational trust engine.

Supports dynamic intent and objection detection across multilingual
(English, Telugu, Hindi, Indian English, and code-mixed) dialogues.
Categorizes objections, supports multiple simultaneous concerns (e.g. Trust + Price),
and supplies empathetic, conversational guidance and counter-framing.
"""

from __future__ import annotations

import re
from jkr_conversation.language import lang_prefix

# Primary objection & concern categories
CAT_PRICE = "price"
CAT_TRUST = "trust"
CAT_NEED_VALUE = "need_value"
CAT_COMPETITOR = "competitor"
CAT_TIMING_BUSY = "timing_busy"
CAT_DISCUSS_TEAM = "discuss_team"
CAT_SEND_DETAILS = "send_details"
CAT_NOT_INTERESTED = "not_interested"
CAT_HOW_IT_WORKS = "how_it_works"
CAT_APPOINTMENT_DOUBTS = "appointment_douBTS"
CAT_HUMAN_REQUEST = "human_request"
CAT_HESITATION = "hesitation"
CAT_RESCHEDULE = "reschedule"
CAT_CANCEL = "cancellation"

ALL_OBJECTION_CATEGORIES = [
    CAT_PRICE,
    CAT_TRUST,
    CAT_NEED_VALUE,
    CAT_COMPETITOR,
    CAT_TIMING_BUSY,
    CAT_DISCUSS_TEAM,
    CAT_SEND_DETAILS,
    CAT_NOT_INTERESTED,
    CAT_HOW_IT_WORKS,
    CAT_APPOINTMENT_DOUBTS,
    CAT_HUMAN_REQUEST,
    CAT_HESITATION,
    CAT_RESCHEDULE,
    CAT_CANCEL,
]

# Multilingual trigger patterns (Telugu, Hindi, English, and Romanized code-mixing)
_TRIGGERS: dict[str, list[str]] = {
    CAT_PRICE: [
        "price", "cost", "expensive", "how much", "rate", "fee", "discount", "offer", "budget", "affordable", "charges",
        "special deal", "deal", "concession", "cheaper", "lower price", "reduce", "bargain",
        "ధర", "ఎంత", "ఖరీదు", "కాస్ట్", "డిస్కౌంట్", "ఎక్కువ", "dhara", "entha", "kharidu", "cost ekkuva", "chala cost",
        "कीमत", "कितना", "दाम", "महंगा", "डिस्काउंट", "खर्चा", "daam", "mehenga", "kitna kharcha", "paisa", "kitne ka hai", "kam karo",
    ],
    CAT_TRUST: [
        "trust", "genuine", "fraud", "fake", "guarantee", "proof", "reliable", "scam", "how do i know", "believe",
        "real ai", "legit", "is this real", "who are you really",
        "నమ్మకం", "నమ్మవచ్చా", "జెన్యూన్", "నిజమేనా", "nammakam", "nammavacha", "genuine aa", "nijamena", "real aa",
        "भरोसा", "विश्वास", "गारंटी", "असली", "धोखा", "bharosa", "vishwas", "asli hai ya nakli", "kaise vishwas kare",
    ],
    CAT_NEED_VALUE: [
        "why should i", "why use", "how does this help", "what is the benefit", "not needed", "don't need", "why this",
        "నాకు ఎందుకు", "నాకేం ఉపయోగం", "ఉపయోగం", "ఎందుకు వాడాలి", "naaku enduku", "upayogam enti", "enduku vadali",
        "मुझे क्यों चाहिए", "क्या फायदा", "क्या लाभ", "kya fayda", "kyun lu", "kya benefit hai",
    ],
    CAT_COMPETITOR: [
        "already have", "already using", "other solution", "another company", "another vendor", "competitor", "different doctor",
        "choose you over", "better than", "other clinic", "other doctor", "apollo", "clove", "versus", "vs", "compared to",
        "వేరే ఉంది", "ఇప్పటికే", "వాడుతున్నాము", "వాడుతున్నాం", "వేరే సాఫ్ట్‌వేర్", "వేరే కంపెనీ", "వేరే హాస్పిటల్", "vere undi", "ippatike", "ippatike vaduthunnamu", "vere clinic",
        "पहले से है", "पहले से", "दूसरा इस्तेमाल", "दूसरी कंपनी", "pehle se hai", "doosra use kar rahe hai", "doosra vendor hai",
    ],
    CAT_TIMING_BUSY: [
        "busy", "driving", "meeting", "call later", "call tomorrow", "not a good time", "call back", "in a rush",
        "different time", "different day", "busy that day", "not free then", "another time",
        "బిజీ", "ఇప్పుడు కుదరదు", "డ్రైవింగ్", "తర్వాత చేయండి", "తర్వాత మాట్లాడదాం", "ippudu kudaradu", "tharuvatha call cheyyandi",
        "వ్యस्त", "बिजी", "मीटिंग", "बाद में कॉल", "अभी समय नहीं है", "drive kar raha hu", "baad me call karna", "abhi busy hu",
    ],
    CAT_HESITATION: [
        "let me think", "thinking about it", "not sure", "not sure right now", "confused", "give me time", "need some time",
        "आలోచించి", "ఆలోచించుకుంటా", "alochinchi", "alochinchukuntanu",
        "सोच कर", "सोचता हूँ", "soch ke", "samay chahiye",
    ],
    CAT_RESCHEDULE: [
        "reschedule", "change appointment", "move my appointment", "postpone", "postponed", "change the date", "change time",
        "వేరే రోజు", "మరో రోజు మార్చండి", "మార్చండి", "reschedule cheyyandi",
        "रीशेड्यूल", "तारीख बदल", "समय बदलो", "बाद के लिए कर दो",
    ],
    CAT_CANCEL: [
        "cancel", "cancellation", "cancel appointment", "cancel my appointment", "cancel the visit", "don't want to come",
        "రద్దు", "క్యాన్సిల్", "వద్దు అపాయింట్‌మెంట్", "cancel cheyyandi",
        "रद्द", "कैंसिल", "अपॉइंटमेंट रद्द", "नहीं आ पाऊँगा",
    ],
    CAT_DISCUSS_TEAM: [
        "discuss with", "husband", "wife", "family", "team", "partner", "boss", "parents", "colleague", "talk to my",
        "భర్త", "భార్య", "కుటుంబం", "మాట్లాడి చెప్తాను", "మా టీమ్", "family tho matladali", "matladi cheptha", "adigi cheptha",
        "पति", "पत्नी", "परिवार", "टीम", "पूछ कर बताऊंगा", "baat karke batata hu", "ghar pe baat karni hai", "team se discuss",
    ],
    CAT_SEND_DETAILS: [
        "send details", "send me the details", "send me details", "send the details", "send on whatsapp", "send over whatsapp", "details on whatsapp", "whatsapp", "send brochure", "brochure", "send info", "share details", "email me", "message me",
        "వాట్సాప్", "వివరాలు పంపండి", "మెసేజ్ చేయండి", "whatsapp lo pampandi", "details pampandi", "message cheyyandi",
        "व्हाट्सऐप", "डिटेल्स भेज दो", "जानकारी भेजो", "whatsapp pe bhej do", "details bhejiye", "brochure bhej do",
    ],
    CAT_NOT_INTERESTED: [
        "not interested", "no interest", "don't want", "no thanks", "not looking", "not interested at all", "really not interested", "leave me alone",
        "వద్దు", "నాకు ఇష్టం లేదు", "ఆసక్తి లేదు", "vaddu", "naaku vaddu", "asakti ledu", "interest ledu",
        "रुचि नहीं है", "नहीं चाहिए", "मत करो", "nahi chahiye", "interest nahi hai", "manaa kar raha hu",
    ],
    CAT_HOW_IT_WORKS: [
        "how does it work", "how it works", "tell me how", "explain the process", "what is the procedure",
        "ఎలా పనిచేస్తుంది", "ఎలా వర్క్ అవుతుంది", "విధానం ఏమిటి", "ela work avutundi", "ela panichesthundi", "process enti",
        "कैसे काम करता है", "तरीका क्या है", "समझाओ", "kaise kaam karta hai", "process kya hai", "kaise hota hai",
    ],
    CAT_APPOINTMENT_DOUBTS: [
        "what happens in appointment", "during appointment", "why appointment", "is consultation free", "what will doctor do",
        "అపాయింట్‌మెంట్‌లో ఏం జరుగుతుంది", "కన్సల్టేషన్ ఫ్రీ నా", "appointment lo em jaruguthundi", "consultation ela untundi",
        "अपॉइंटमेंट में क्या होगा", "कंसल्टेशन में क्या होगा", "appointment me kya hoga", "doctor kya karenge",
    ],
    CAT_HUMAN_REQUEST: [
        "human", "real person", "talk to someone", "representative", "manager", "operator", "agent",
        "మనిషితో మాట్లాడాలి", "మనిషి", "manishitho matladali", "person tho matladali", "agent tho matladali",
        "इंसान से बात", "किसी आदमी से", "इंसान", "insan se baat", "kisi representative se baat karao",
    ],
}

_SPOKEN_COUNTER_FRAMING: dict[str, dict[str, str]] = {
    CAT_PRICE: {
        "te": "ధర విషయానికి వస్తే, మా ప్లాన్స్‌ చాలా పారదర్శకంగా మరియు రీజనబుల్‌గా ఉంటాయి అండి. మీ అవసరాలకు తగిన ఉత్తమ ఆప్షన్‌ను మేము సూచిస్తాము.",
        "hi": "कीमत के बारे में बताऊँ तो, हमारे प्लान्स बहुत पारदर्शी और वाजिब हैं। आपकी ज़रूरत के अनुसार हम सबसे सही विकल्प बता देंगे।",
        "en": "Regarding pricing, our rates are completely transparent and standardized with no hidden charges. We can also check if any promotional packages apply.",
    },
    CAT_TRUST: {
        "te": "మీ సందేహం అర్థమైంది అండి. నేను Aaha Dental Care అధికారిక AI వాయిస్ అసిస్టెంట్‌ని. మా వద్ద సర్టిఫైడ్ డెంటిస్ట్‌లు ఉన్నారు.",
        "hi": "मैं आपका संशय समझ सकता हूँ। मैं अधिकृत एआई असिस्टेंट हूँ और हमारे पास प्रमाणित डॉक्टरों की टीम है।",
        "en": "I completely understand your skepticism! I am the verified AI assistant for Aaha Dental Care, and you can confirm our clinic credentials anytime.",
    },
    CAT_NEED_VALUE: {
        "te": "ముఖ్యమైన విషయం ఏమిటంటే, ఇది మీ సమయాన్ని ఆదా చేస్తుంది మరియు మీ సమస్యను సులభంగా పరిష్కరిస్తుంది అండి.",
        "hi": "सबसे मुख्य बात यह है कि यह आपका समय बचाता है और आपके काम को बेहद आसान बना देता है।",
        "en": "The main benefit is that it saves you valuable time and provides a smooth, reliable solution to your exact problem.",
    },
    CAT_COMPETITOR: {
        "te": "మంచిది అండి. వేరే క్లినిక్‌లు ఉన్నా, మా ప్రత్యేకత ఏంటంటే అనుభవజ్ఞులైన వైద్యులు మరియు వేగవంతమైన వ్యక్తిగత సంరక్షణ.",
        "hi": "बहुत अच्छी बात है। दूसरे क्लीनिक के होते हुए भी, हमारी खासियत है अनुभवी डॉक्टर, आधुनिक तकनीक और तुरंत व्यक्तिगत सेवा।",
        "en": "Those are respected providers, but at Aaha Dental Care we focus on personalized one-on-one attention, experienced specialists, and flexible scheduling.",
    },
    CAT_TIMING_BUSY: {
        "te": "తప్పకుండా అండి, మీరు బిజీగా ఉన్నారని అర్థమైంది. మీకు వీలైనప్పుడు కాల్ చేయమంటారా, లేదా వాట్సాప్‌లో వివరాలు పంపమంటారా?",
        "hi": "बिल्कुल, मैं समझता हूँ आप अभी व्यस्त हैं। क्या मैं आपको बाद में कॉल करूँ या व्हाट्सऐप पर डिटेल्स भेज दूँ?",
        "en": "I completely understand you have a busy schedule. We can easily find an alternate time or weekend slot that works perfectly for you.",
    },
    CAT_HESITATION: {
        "te": "తప్పకుండా అండి, ఆలోచించుకోండి! మీకు పరిశీలించడానికి వాట్సాప్‌లో పూర్తి వివరాలు పంపమంటారా?",
        "hi": "बिल्कुल, आप आराम से सोच लीजिए! क्या मैं व्हाट्सऐप पर पूरी जानकारी भेज दूँ ताकि आप जब चाहें देख सकें?",
        "en": "Take all the time you need! I can send the complete details and pricing to your WhatsApp so you can review it at your convenience.",
    },
    CAT_RESCHEDULE: {
        "te": "ఖచ్చితంగా అండి, అపాయింట్‌మెంట్‌ను మార్చడం చాలా సులభం. మీకు వచ్చే వారం ఏ రోజు మరియు సమయం వీలవుతుందో చెప్పండి.",
        "hi": "बिल्कुल, अपॉइंटमेंट बदलना बहुत आसान है। अगले हफ्ते आपके लिए कौन सा दिन और समय सबसे सही रहेगा?",
        "en": "No problem at all, we can easily reschedule that for you! What day or time next week would suit you best?",
    },
    CAT_CANCEL: {
        "te": "సరే అండి, మీ అపాయింట్‌మెంట్ రద్దు చేశాము. భవిష్యత్తులో ఎప్పుడైనా అవసరమైతే మేము అందుబాటులో ఉంటాము.",
        "hi": "कोई बात नहीं, मैंने आपका अपॉइंटमेंट रद्द कर दिया है। भविष्य में कभी भी ज़रूरत हो तो हमें ज़रूर बताइएगा।",
        "en": "I understand completely, and I have noted the cancellation. Please feel free to reach out whenever you'd like to schedule in the future.",
    },
    CAT_DISCUSS_TEAM: {
        "te": "ఖచ్చితంగా అండి, కుటుంబంతో లేదా టీమ్‌తో చర్చించడం చాలా ముఖ్యం. వారు కూడా పరిశీలించేందుకు వాట్సాప్‌లో సమాచారం పంపమంటారా?",
        "hi": "बिल्कुल, परिवार या टीम से सलाह लेना ज़रूरी है। क्या मैं व्हाट्सऐप पर जानकारी भेज दूँ ताकि वो भी देख सकें?",
        "en": "Of course, discussing with your family or team is very important. I can send the overview via WhatsApp so you can review together.",
    },
    CAT_SEND_DETAILS: {
        "te": "తప్పకుండా అండి, మీ నంబర్‌కు వాట్సాప్‌లో పూర్తి వివరాలు మరియు బ్రోచర్ వెంటనే పంపుతాము.",
        "hi": "ज़रूर, मैं आपके नंबर पर व्हाट्सऐप पर तुरंत पूरी जानकारी भेज देता हूँ।",
        "en": "Certainly, I'll have the complete details and brochure sent directly to your WhatsApp right away.",
    },
    CAT_NOT_INTERESTED: {
        "te": "అర్థమైంది అండి, ఇబ్బంది కలిగించినందుకు క్షమించండి. భవిష్యత్తులో ఎప్పుడైనా అవసరమైతే మేము అందుబాటులో ఉంటాము. ధన్యవాదాలు!",
        "hi": "समझ गया, आपको परेशानी हुई तो माफ़ी चाहते हैं। भविष्य में कभी भी ज़रूरत हो तो हम यहाँ हैं। धन्यवाद!",
        "en": "Understood, I completely respect that. If you ever need help in the future, we're always here. Have a great day!",
    },
    CAT_HOW_IT_WORKS: {
        "te": "విధానం చాలా సులభం అండి. ముందుగా మీ అవసరాలు పరిశీలించి, సరైన మార్గదర్శకత్వం అందిస్తాము.",
        "hi": "प्रक्रिया बहुत सीधी है। पहले हम आपकी ज़रूरत समझते हैं, और फिर सही समाधान और प्लान देते हैं।",
        "en": "The process is very simple. First, we understand your exact requirements, and then guide you through the ideal solution.",
    },
    CAT_APPOINTMENT_DOUBTS: {
        "te": "అపాయింట్‌మెంట్ చాలా సౌకర్యవంతంగా ఉంటుంది అండి. నిపుణులు మీ సందేహాలను పూర్తిగా నివృత్తి చేస్తారు.",
        "hi": "अपॉइंटमेंट बिल्कुल आसान और सुविधाजनक है। विशेषज्ञ आपके सभी सवालों के जवाब देंगे और सही राय देंगे।",
        "en": "The consultation is quick and obligation-free. Our specialist will directly address all your questions and provide clear guidance.",
    },
}


def detect_objections(text: str) -> list[str]:
    """Detects all matching objection and concern categories in customer utterance."""
    if not text or not text.strip():
        return []

    lowered = text.lower()
    matches: list[str] = []

    for category, triggers in _TRIGGERS.items():
        for trig in triggers:
            if trig in lowered:
                if category not in matches:
                    matches.append(category)
                break

    return matches


def build_objection_guidance(categories: list[str], language: str = "en") -> str:
    """Builds LLM prompt instruction guidance tailored to the detected objections."""
    if not categories:
        return ""

    lp = lang_prefix(language)
    guidance_parts: list[str] = []

    for cat in categories:
        if cat == CAT_PRICE:
            guidance_parts.append(
                "Address the customer's price inquiry or concern empathetically. Clarify value and transparency from approved knowledge. Do not invent discounts or fake pricing."
            )
        elif cat == CAT_TRUST:
            guidance_parts.append(
                "Reassure the customer with factual credibility and verified track record from approved knowledge. Never sound defensive."
            )
        elif cat == CAT_NEED_VALUE:
            guidance_parts.append(
                "Explain the concrete, practical benefits clearly and simply. Focus on how it solves their problem."
            )
        elif cat == CAT_COMPETITOR:
            guidance_parts.append(
                "Acknowledge their existing solution respectfully. Highlight our speed, dedicated care, and unique strengths without speaking ill of competitors."
            )
        elif cat == CAT_TIMING_BUSY:
            guidance_parts.append(
                "Respect the customer's time immediately. Offer a callback at their convenience or offer to send details on WhatsApp."
            )
        elif cat == CAT_DISCUSS_TEAM:
            guidance_parts.append(
                "Validate discussing with family or team members. Offer to send a summary over WhatsApp to share with them."
            )
        elif cat == CAT_SEND_DETAILS:
            guidance_parts.append(
                "Affirm that information and brochure can be shared via WhatsApp, and politely suggest an appointment as the natural next step to review them."
            )
        elif cat == CAT_NOT_INTERESTED:
            guidance_parts.append(
                "Never pressure or aggressively argue. Politely acknowledge, give at most one concise helpful insight, and if they decline, end politely."
            )
        elif cat == CAT_HOW_IT_WORKS:
            guidance_parts.append(
                "Explain the step-by-step process in one or two simple spoken sentences."
            )
        elif cat == CAT_APPOINTMENT_DOUBTS:
            guidance_parts.append(
                "Explain what happens during the appointment: a brief, friendly, obligation-free consultation where questions are answered."
            )
        elif cat == CAT_HESITATION:
            guidance_parts.append(
                "Acknowledge their hesitation warmly without pressuring them. Offer to send a summary or pricing over WhatsApp so they can review in their own time, or offer a callback later."
            )
        elif cat == CAT_RESCHEDULE:
            guidance_parts.append(
                "Acknowledge the reschedule request warmly and helpfully. Reassure the customer that changing the appointment is completely fine, and ask for their preferred new day or time."
            )
        elif cat == CAT_CANCEL:
            guidance_parts.append(
                "Accept the cancellation gracefully and politely. Do not argue or guilt-trip them. Confirm that their cancellation is noted and they are welcome back anytime."
            )

    return " ".join(guidance_parts)


def get_spoken_objection_fallback(category: str, language: str = "en") -> str:
    """Returns spoken, natural objection fallback text for mock/fast mode."""
    lp = lang_prefix(language)
    cat_dict = _SPOKEN_COUNTER_FRAMING.get(category)
    if not cat_dict:
        return ""
    return cat_dict.get(lp, cat_dict.get("en", ""))
