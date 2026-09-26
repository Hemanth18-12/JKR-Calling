export type TourLanguage = "en-IN" | "te-IN" | "hi-IN";

export interface TourStep {
  id: string; // The DOM element ID to highlight
  order: number;
  title: {
    "en-IN": string;
    "te-IN": string;
    "hi-IN": string;
  };
  narration: {
    "en-IN": string;
    "te-IN": string;
    "hi-IN": string;
  };
  highlightName: string;
}

export interface PageTour {
  pageId: string;
  pageTitle: string;
  steps: TourStep[];
}

export const TOUR_SCRIPTS: Record<string, PageTour> = {
  dashboard: {
    pageId: "dashboard",
    pageTitle: "Dashboard Tour",
    steps: [
      {
        id: "tour-quick-actions",
        order: 1,
        highlightName: "Telephony & Quick Action Cards",
        title: {
          "en-IN": "Live Telephony & Quick Actions",
          "te-IN": "లైవ్ టెలిఫోనీ & క్విక్ యాక్షన్స్",
          "hi-IN": "लाइव टेलीफोनी और त्वरित कार्य",
        },
        narration: {
          "en-IN":
            "These quick action cards give you real-time visibility into your Dograh telephony pipeline, direct access to test the AI voice agent in the browser lab, and bulk CSV contact imports.",
          "te-IN":
            "ఈ క్విక్ యాక్షన్ కార్డ్స్ ద్వారా డోగ్రా టెలిఫోనీ పైప్‌లైన్ స్థితిని చూడవచ్చు, బ్రౌజర్ ల్యాబ్‌లో ఏఐ వాయిస్ ఏజెంట్‌ను నేరుగా టెస్ట్ చేయవచ్చు మరియు కాంటాక్ట్‌లను సులభంగా ఇంపోర్ట్ చేసుకోవచ్చు.",
          "hi-IN":
            "ये त्वरित कार्य कार्ड आपको डोग्राह टेलीफोनी पाइपलाइन की लाइव स्थिति दिखाते हैं, जहां से आप ब्राउज़र में वॉयस एजेंट का परीक्षण और संपर्कों को आयात कर सकते हैं।",
        },
      },
      {
        id: "tour-kpi-cards",
        order: 2,
        highlightName: "Core Business KPIs",
        title: {
          "en-IN": "Business Outcome Metrics",
          "te-IN": "కీలక వ్యాపార కొలమానాలు",
          "hi-IN": "प्रमुख व्यावसायिक मेट्रिक्स",
        },
        narration: {
          "en-IN":
            "Here you can track your vital calling outcomes: total calls dialed, connect rate, booked appointments, and unique contacts reached across all campaigns.",
          "te-IN":
            "ఇక్కడ మీ ముఖ్యమైన ఫలితాలను చూడవచ్చు: మొత్తం కాల్స్, కనెక్ట్ రేటు, బుక్ అయిన అపాయింట్‌మెంట్లు మరియు రీచ్ అయిన కస్టమర్ల సంఖ్య.",
          "hi-IN":
            "यहां आप अपने महत्वपूर्ण कॉलिंग परिणाम देख सकते हैं: कुल कॉल, कनेक्ट दर, बुक किए गए अपॉइंटमेंट और संपर्क किए गए ग्राहक।",
        },
      },
      {
        id: "tour-roi-ticker",
        order: 3,
        highlightName: "Cost-Per-Outcome ROI Ticker",
        title: {
          "en-IN": "Unit Economics & Savings",
          "te-IN": "యూనిట్ ఎకనామిక్స్ & పొదుపు",
          "hi-IN": "लागत और बचत विश्लेषण",
        },
        narration: {
          "en-IN":
            "This real-time ROI ticker calculates your true AI acquisition cost per booked appointment compared to human BDR benchmarks, showing seventy-five to eighty-five percent cost reduction.",
          "te-IN":
            "ఈ రియల్-టైమ్ ఆర్ఓఐ టిక్కర్ మానవ ప్రతినిధుల ఖర్చులతో పోలిస్తే ప్రతి బుకింగ్‌పై డెబ్బై ఐదు నుండి ఎనభై ఐదు శాతం వరకు వ్యయ పొదుపును లెక్కిస్తుంది.",
          "hi-IN":
            "यह रीयल-टाइम आरओआई टिकर पारंपरिक मानव कॉलिंग लागत की तुलना में प्रति अपॉइंटमेंट पचहत्तर से पचासी प्रतिशत तक बचत प्रदर्शित करता है।",
        },
      },
      {
        id: "tour-recent-calls",
        order: 4,
        highlightName: "Recent Call Outcomes",
        title: {
          "en-IN": "Recent Live Call Stream",
          "te-IN": "ఇటీవలి లైవ్ కాల్స్",
          "hi-IN": "हाल ही के कॉल परिणाम",
        },
        narration: {
          "en-IN":
            "Review your latest calls with live agent disposition tags, timestamps, and direct click-through access into complete audio recordings and bilingual transcripts.",
          "te-IN":
            "ఇటీవలి కాల్‌ల ఫలితాలు, ఏజెంట్ నిర్ణయాలు, ఆడియో రికార్డింగ్‌లు మరియు తెలుగు-ఇంగ్లీష్ ట్రాన్స్‌క్రిప్ట్‌లను ఇక్కడ నేరుగా సమీక్షించవచ్చు.",
          "hi-IN":
            "अपने नवीनतम कॉल्स की समीक्षा करें, जिसमें लाइव एजेंट टैग, ऑडियो रिकॉर्डिंग और द्विभाषी ट्रांसक्रिप्ट शामिल हैं।",
        },
      },
    ],
  },
  campaigns: {
    pageId: "campaigns",
    pageTitle: "Campaigns Tour",
    steps: [
      {
        id: "tour-campaigns-header",
        order: 1,
        highlightName: "Ten-Check Safety Model",
        title: {
          "en-IN": "Compliance & Safety Gate",
          "te-IN": "సేఫ్టీ & నిబంధనల రక్షణ",
          "hi-IN": "सुरक्षा और अनुपालन मॉडल",
        },
        narration: {
          "en-IN":
            "Every outbound campaign is guarded by our ten-check safety gate, strictly enforcing local calling hours, explicit consent, and Do Not Disturb suppression.",
          "te-IN":
            "ప్రతి ఔట్‌బౌండ్ ప్రచారం మా పది సేఫ్టీ చెక్కుల ద్వారా మాత్రమే పనిచేస్తుంది, ఇది కాలింగ్ సమయాలు మరియు సమ్మతిని కచ్చితంగా పాటిస్తుంది.",
          "hi-IN":
            "प्रत्येक आउटबाउंड अभियान हमारे दस-चरणीय सुरक्षा मॉडल द्वारा नियंत्रित होता है, जो कॉलिंग समय और सहमति की पुष्टि करता है।",
        },
      },
      {
        id: "tour-new-campaign-btn",
        order: 2,
        highlightName: "Create & Dry Run Campaigns",
        title: {
          "en-IN": "Launch Targeted Campaigns",
          "te-IN": "కొత్త ప్రచారం ప్రారంభించండి",
          "hi-IN": "नया अभियान शुरू करें",
        },
        narration: {
          "en-IN":
            "Click New Campaign to select a published multilingual agent, define calling windows, and simulate your dispatch with a safe dry run before live dialing.",
          "te-IN":
            "ప్రచురించిన ఏజెంట్‌ను ఎంచుకోవడానికి మరియు సురక్షితమైన డ్రై రన్ పరీక్షించడానికి 'న్యూ క్యాంపెయిన్' పై క్లిక్ చేయండి.",
          "hi-IN":
            "प्रकाशित एजेंट का चयन करने और सुरक्षित ड्राई रन के साथ अभियान का परीक्षण करने के लिए 'न्यू कैंपेन' पर क्लिक करें।",
        },
      },
    ],
  },
  calls: {
    pageId: "calls",
    pageTitle: "Calls Tour",
    steps: [
      {
        id: "tour-calls-filter",
        order: 1,
        highlightName: "Call Filters & Modes",
        title: {
          "en-IN": "Filter by Source",
          "te-IN": "కాల్ ఫిల్టర్లు",
          "hi-IN": "कॉल फ़िल्टर",
        },
        narration: {
          "en-IN":
            "Toggle between all calls, outbound campaign dispatches, and interactive browser test lab sessions with instant outcome counts.",
          "te-IN":
            "ఇక్కడ మీరు అన్ని కాల్స్‌ను క్యాంపెయిన్ లేదా టెస్ట్ ల్యాబ్ ఆధారంగా సులభంగా ఫిల్టర్ చేసి చూడవచ్చు.",
          "hi-IN":
            "यहां आप सभी कॉल्स, अभियान कॉल और टेस्ट लैब सत्रों के बीच आसानी से फ़िल्टर कर सकते हैं।",
        },
      },
      {
        id: "tour-calls-list",
        order: 2,
        highlightName: "Call Logs & Recording Detail",
        title: {
          "en-IN": "Call Log Records",
          "te-IN": "కాల్ రికార్డులు & వివరాలు",
          "hi-IN": "कॉल लॉग और रिकॉर्डिंग",
        },
        narration: {
          "en-IN":
            "Select any call row to open the complete call drawer, view synchronized audio playback, inspect turn-by-turn transcripts, and verify booked appointments.",
          "te-IN":
            "ఏదైనా కాల్‌పై క్లిక్ చేసి పూర్తి ఆడియో ప్లేబ్యాక్, సంభాషణ వివరాలు మరియు లీడ్ సమాచారాన్ని పరిశీలించవచ్చు.",
          "hi-IN":
            "किसी भी कॉल पर क्लिक करके संपूर्ण ऑडियो प्लेबैक, बातचीत की प्रतिलिपि और बुक किए गए अपॉइंटमेंट देख सकते हैं।",
        },
      },
    ],
  },
  live_console: {
    pageId: "live_console",
    pageTitle: "Live Console Tour",
    steps: [
      {
        id: "tour-live-queue",
        order: 1,
        highlightName: "Active Calls Queue",
        title: {
          "en-IN": "Active Calls Stream",
          "te-IN": "యాక్టివ్ కాల్స్ స్ట్రీమ్",
          "hi-IN": "सक्रिय कॉल कतार",
        },
        narration: {
          "en-IN":
            "The Live Console shows all ongoing calls in real time, driven by low-latency server-sent events as the conversation unfolds.",
          "te-IN":
            "ఈ లైవ్ కన్సోల్ ప్రస్తుతం జరుగుతున్న అన్ని లైవ్ కాల్స్‌ను రియల్ టైమ్ సర్వర్-సెంట్ ఈవెంట్ల ద్వారా చూపిస్తుంది.",
          "hi-IN":
            "लाइव कंसोल वर्तमान में चल रहे सभी कॉल्स को रीयल-टाइम में दिखाता है।",
        },
      },
      {
        id: "tour-live-transcript",
        order: 2,
        highlightName: "Real-Time Bilingual Transcript",
        title: {
          "en-IN": "Live Conversation Transcript",
          "te-IN": "లైవ్ సంభాషణ ట్రాన్స్‌క్రిప్ట్",
          "hi-IN": "लाइव बातचीत का विवरण",
        },
        narration: {
          "en-IN":
            "Follow the conversation live in Telugu, Hindi, or English. You can see speech-to-text turns, intent detection, and AI responses as they happen.",
          "te-IN":
            "కస్టమర్ మరియు ఏజెంట్ సంభాషణను తెలుగు లేదా ఇంగ్లీషులో రియల్ టైమ్‌లో చదవవచ్చు మరియు ట్రాక్ చేయవచ్చు.",
          "hi-IN":
            "ग्राहक और एजेंट के बीच बातचीत को हिंदी, तेलुगु या अंग्रेजी में लाइव पढ़ें और ट्रैक करें।",
        },
      },
      {
        id: "tour-live-controls",
        order: 3,
        highlightName: "Supervisor Intervention Controls",
        title: {
          "en-IN": "Listen In & Whisper Controls",
          "te-IN": "సూపర్‌వైజర్ నియంత్రణలు",
          "hi-IN": "सुपरवाइजर नियंत्रण",
        },
        narration: {
          "en-IN":
            "Supervisors can listen in silently, whisper real-time hints directly into the AI agent's prompt context, or barge in to immediately take over the call.",
          "te-IN":
            "సూపర్‌వైజర్లు ఇక్కడి నుండి కాల్ వినవచ్చు, ఏజెంట్‌కు లైవ్ సలహాలు ఇవ్వవచ్చు లేదా అవసరమైనప్పుడు నేరుగా మాట్లాడవచ్చు.",
          "hi-IN":
            "सुपरवाइजर बातचीत सुन सकते हैं, एआई को लाइव संकेत भेज सकते हैं या कॉल का नियंत्रण अपने हाथ में ले सकते हैं।",
        },
      },
    ],
  },
  analytics: {
    pageId: "analytics",
    pageTitle: "Analytics Tour",
    steps: [
      {
        id: "tour-analytics-kpi",
        order: 1,
        highlightName: "Funnel & Outcome Breakdown",
        title: {
          "en-IN": "Conversion Funnel",
          "te-IN": "కన్వర్షన్ ఫన్నెల్",
          "hi-IN": "रूपांतरण फ़नल",
        },
        narration: {
          "en-IN":
            "Track full-funnel conversion from dials to answered calls, lead qualification, and booked appointments.",
          "te-IN":
            "డయల్ చేసిన కాల్స్ నుండి క్వాలిఫైడ్ మరియు బుకింగ్స్ వరకు పూర్తి కన్వర్షన్ వివరాలను ఇక్కడ విశ్లేషించవచ్చు.",
          "hi-IN":
            "डायल से लेकर क्वालिफिकेशन और अपॉइंटमेंट बुकिंग तक पूरे रूपांतरण फ़नल को ट्रैक करें।",
        },
      },
      {
        id: "tour-analytics-regional",
        order: 2,
        highlightName: "Regional & Multilingual Distribution",
        title: {
          "en-IN": "India State & Language Insights",
          "te-IN": "ప్రాంతీయ & భాషా గణాంకాలు",
          "hi-IN": "क्षेत्रीय और भाषा अंतर्दृष्टि",
        },
        narration: {
          "en-IN":
            "See call pickup rates and language adoption across Indian states, highlighting Telugu, Hindi, and English code-switching performance.",
          "te-IN":
            "భారతదేశంలోని వివిధ రాష్ట్రాల వారీగా కనెక్ట్ రేట్లు మరియు తెలుగు, హిందీ, ఇంగ్లీష్ భాషల వాడకాన్ని ఇక్కడ చూడవచ్చు.",
          "hi-IN":
            "भारतीय राज्यों में कॉल पिकअप दर और तेलुगु, हिंदी व अंग्रेजी भाषा के उपयोग का विश्लेषण देखें।",
        },
      },
      {
        id: "tour-analytics-voice-health",
        order: 3,
        highlightName: "Telephony & Voice Health Latency",
        title: {
          "en-IN": "p95 Pipeline Latency",
          "te-IN": "వాయిస్ పైప్‌లైన్ వేగం",
          "hi-IN": "वॉयस पाइपलाइन लेटेंसी",
        },
        narration: {
          "en-IN":
            "Monitor end-to-end voice latency including Sarvam STT transcription, LLM reasoning, and Sarvam Bulbul TTS synthesis to ensure human-speed conversations.",
          "te-IN":
            "సర్వం ఎస్టీటీ, ఎల్ఎల్ఎమ్ మరియు సర్వం బుల్‌బుల్ టీటీఎస్ సింథసిస్ లేటెన్సీని నిరంతరం పర్యవేక్షించి సంభాషణల వేగాన్ని నిర్ధారించండి.",
          "hi-IN":
            "सर्वम भाषण पहचान और टीटीएस संश्लेषण की लेटेंसी की निगरानी करें ताकि बातचीत स्वाभाविक गति से चले।",
        },
      },
    ],
  },
};
