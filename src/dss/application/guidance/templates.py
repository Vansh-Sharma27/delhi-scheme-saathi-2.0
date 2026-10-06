"""Deterministic multilingual conversation templates."""

from src.dss.application.guidance.localization import _pick_language_text


def generate_greeting_response(language: str = "hi") -> str:
    """Generate greeting response without LLM."""
    greetings = {
        "hi": (
            "नमस्ते! 🙏 मैं दिल्ली स्कीम साथी हूं।\n\n"
            "मैं आपको सरकारी योजनाओं की जानकारी देने में मदद कर सकता हूं:\n"
            "• घर खरीदना/बनाना\n"
            "• स्वास्थ्य सहायता\n"
            "• शिक्षा ऋण\n"
            "• पेंशन योजनाएं\n"
            "• रोजगार सहायता\n\n"
            "आप मुझे बताएं, आज आपको किस तरह की सहायता चाहिए?"
        ),
        "en": (
            "Namaste! 🙏 I am Delhi Scheme Saathi.\n\n"
            "I can help you with government welfare schemes for:\n"
            "• Housing assistance\n"
            "• Health support\n"
            "• Education loans\n"
            "• Pension schemes\n"
            "• Employment support\n\n"
            "Please tell me, what kind of assistance do you need today?"
        ),
        "hinglish": (
            "Namaste! 🙏 Main Delhi Scheme Saathi hoon.\n\n"
            "Main aapko government welfare schemes mein help kar sakta hoon:\n"
            "• Housing assistance\n"
            "• Health support\n"
            "• Education loans\n"
            "• Pension schemes\n"
            "• Employment support\n\n"
            "Batayiye, aaj aapko kis tarah ki madad chahiye?"
        ),
    }
    return greetings.get(language, greetings["en"])


def generate_help_response(
    language: str = "auto",
    *,
    has_active_scheme: bool = False,
) -> str:
    """Generate a deterministic help guide for users and judges."""
    generic_responses = {
        "hi": (
            "दिल्ली स्कीम साथी आपकी स्थिति के हिसाब से उपयोगी दिल्ली सरकारी योजनाएं समझने में मदद करता है।\n\n"
            "इसे कैसे उपयोग करें:\n"
            "• अपनी जरूरत एक सरल वाक्य में बताएं\n"
            '  उदाहरण: "मुझे विधवा पेंशन की जानकारी चाहिए"\n'
            "• अगर पूछा जाए तो उम्र, श्रेणी, आय, लिंग या स्थिति बताएं\n"
            "• किसी योजना पर आगे पूछें: पात्रता, लाभ, दस्तावेज, आवेदन प्रक्रिया, या यह योजना क्यों दिखाई गई\n"
            "• विषय बदलना हो तो सीधे कहें: अब मुझे किसी और मदद की जरूरत है\n\n"
            "उपयोगी कमांड और वाक्य:\n"
            "• /help : यह गाइड फिर से देखें\n"
            "• /language : भाषा बदलें\n"
            "• /start : नई खोज शुरू करें\n"
            '• "start over" या "restart" : चैट अपने-आप रीसेट करें\n'
            '• "bye" : बातचीत समाप्त करें\n\n'
            "अभी यह बॉट क्या कर सकता है:\n"
            "• दिल्ली की संबंधित योजनाएं ढूंढना\n"
            "• योजना को सरल भाषा में समझाना\n"
            "• आपकी दी हुई जानकारी के आधार पर संभावित पात्रता बताना\n"
            "• दस्तावेज, आवेदन चरण, और rejection warnings बताना\n"
            "• हिंदी, अंग्रेज़ी, और हिंग्लिश में जवाब देना\n\n"
            "महत्वपूर्ण:\n"
            "यह मार्गदर्शन के लिए है। अंतिम पात्रता और मंजूरी सरकारी नियमों और दस्तावेज़ सत्यापन पर निर्भर करती है।"
        ),
        "en": (
            "Delhi Scheme Saathi helps you understand which Delhi government welfare schemes may fit your situation.\n\n"
            "How to use it:\n"
            "• Start with one simple need\n"
            '  Example: "I need widow pension help"\n'
            "• Answer short questions like age, category, income, gender, or situation\n"
            "• Ask follow-up questions about eligibility, benefits, documents, application steps, or why a scheme was suggested\n"
            "• If your need changes, just say so and the bot can switch topics\n\n"
            "Useful commands and phrases:\n"
            "• /help : show this guide again\n"
            "• /language : change language\n"
            "• /start : begin a fresh search\n"
            '• "start over" or "restart" : reset the chat automatically\n'
            '• "bye" : end the conversation\n\n'
            "Current capabilities:\n"
            "• Find relevant Delhi welfare schemes\n"
            "• Explain scheme details in simple language\n"
            "• Share likely eligibility based on the details you provide\n"
            "• List documents, application steps, and common rejection warnings\n"
            "• Reply in English, Hindi, or Hinglish\n\n"
            "Important:\n"
            "This bot is a guidance tool. Final eligibility and approval depend on official government rules and document verification."
        ),
        "hinglish": (
            "Delhi Scheme Saathi aapki situation ke hisaab se useful Delhi government schemes samajhne mein help karta hai.\n\n"
            "Use kaise karein:\n"
            "• Apni need ek simple sentence mein batayiye\n"
            '  Example: "Mujhe widow pension help chahiye"\n'
            "• Agar poocha jaye toh age, category, income, gender ya situation batayiye\n"
            "• Scheme ke baare mein follow-up pooch sakte hain: eligibility, benefits, documents, application steps, ya yeh scheme kyon dikhayi gayi\n"
            "• Topic badalna ho toh seedha bol dijiye\n\n"
            "Useful commands aur phrases:\n"
            "• /help : yeh guide phir se dekhiye\n"
            "• /language : language badaliye\n"
            "• /start : fresh search shuru kijiye\n"
            '• "start over" ya "restart" : chat automatically reset ho jayegi\n'
            '• "bye" : conversation khatam kijiye\n\n'
            "Current capabilities:\n"
            "• Relevant Delhi welfare schemes dhoondhna\n"
            "• Scheme details simple language mein samjhana\n"
            "• Aapki details ke basis par likely eligibility batana\n"
            "• Documents, application steps, aur common rejection warnings batana\n"
            "• English, Hindi, aur Hinglish mein reply karna\n\n"
            "Important:\n"
            "Yeh guidance tool hai. Final eligibility aur approval official rules aur document verification par depend karta hai."
        ),
    }
    scheme_context_responses = {
        "hi": (
            "आप इस समय एक चुनी हुई योजना देख रहे हैं। इसी योजना पर आप सीधे ये सवाल पूछ सकते हैं:\n"
            "• क्या मैं पात्र हूं?\n"
            "• यह योजना क्यों दिखाई गई?\n"
            "• कौन-कौन से दस्तावेज चाहिए?\n"
            "• आवेदन कैसे करें?\n"
            "• किन गलतियों से बचना चाहिए?\n\n"
            "उपयोगी कमांड:\n"
            "• /language : भाषा बदलें\n"
            "• /start : नई खोज शुरू करें\n"
            '• "start over" : बातचीत रीसेट करें\n'
            '• "bye" : बातचीत समाप्त करें'
        ),
        "en": (
            "You are currently viewing a selected scheme. You can directly ask:\n"
            "• Am I eligible?\n"
            "• Why was this scheme suggested?\n"
            "• What documents are needed?\n"
            "• How do I apply?\n"
            "• What mistakes should I avoid?\n\n"
            "Useful commands:\n"
            "• /language : change language\n"
            "• /start : begin a fresh search\n"
            '• "start over" : reset the conversation\n'
            '• "bye" : end the conversation'
        ),
        "hinglish": (
            "Aap is waqt ek selected scheme dekh rahe hain. Aap seedha pooch sakte hain:\n"
            "• Kya main eligible hoon?\n"
            "• Yeh scheme kyon dikhayi gayi?\n"
            "• Kaun se documents chahiye?\n"
            "• Apply kaise karna hai?\n"
            "• Kin mistakes se bachna chahiye?\n\n"
            "Useful commands:\n"
            "• /language : language badaliye\n"
            "• /start : fresh search shuru kijiye\n"
            '• "start over" : conversation reset kijiye\n'
            '• "bye" : conversation khatam kijiye'
        ),
    }

    responses = scheme_context_responses if has_active_scheme else generic_responses

    if language not in responses:
        return (
            "Delhi Scheme Saathi Help\n\n"
            "ENGLISH\n"
            f"{generic_responses['en']}\n\n"
            "हिंदी\n"
            f"{generic_responses['hi']}"
        )
    return responses[language]


def generate_language_selection_response(language: str = "auto") -> str:
    """Prompt the user to choose a conversation language."""
    responses = {
        "hi": ("कृपया अपनी पसंदीदा भाषा चुनें।\nआप कभी भी /language दबाकर भाषा बदल सकते हैं।"),
        "en": ("Choose your preferred language.\nYou can switch again anytime with /language."),
        "hinglish": (
            "Apni preferred language choose kijiye.\n"
            "Aap kabhi bhi /language se language badal sakte hain."
        ),
    }
    if language not in responses:
        return (
            "Choose your preferred language / अपनी पसंदीदा भाषा चुनें.\n"
            "You can switch again anytime with /language."
        )
    return responses[language]


def generate_language_changed_response(
    language: str,
    *,
    has_active_scheme: bool = False,
) -> str:
    """Confirm language change and suggest what to do next."""
    if has_active_scheme:
        return _pick_language_text(
            language,
            "भाषा बदल दी गई है। अब आप इसी योजना के बारे में पात्रता, दस्तावेज, लाभ, या आवेदन पूछ सकते हैं।",
            "Language updated. You can now continue asking about this scheme's eligibility, documents, benefits, or application steps.",
            "Language update ho gayi hai. Ab aap isi scheme ke baare mein eligibility, documents, benefits, ya application steps pooch sakte hain.",
        )
    return _pick_language_text(
        language,
        "भाषा बदल दी गई है। अब आप अपनी जरूरत बताइए या /help देखिए।",
        "Language updated. You can now tell me your need or use /help.",
        "Language update ho gayi hai. Ab aap apni need batayiye ya /help dekhiye.",
    )


def generate_clarification_response(
    missing_field: str,
    language: str = "hi",
) -> str:
    """Generate response asking for missing information."""
    questions = {
        "life_event": {
            "hi": "आप मुझे बताएं, आज आपको किस तरह की सहायता चाहिए? (जैसे: घर, स्वास्थ्य, शिक्षा, रोजगार)",
            "en": "Please tell me, what kind of assistance do you need? (e.g., housing, health, education, employment)",
            "hinglish": "Batayiye, aaj aapko kis tarah ki madad chahiye? (jaise housing, health, education, employment)",
        },
        "age": {
            "hi": "योजनाओं की पात्रता जाँचने के लिए, कृपया अपनी उम्र बताएं।",
            "en": "To check scheme eligibility, please tell me your age.",
            "hinglish": "Scheme eligibility check karne ke liye, please age batayiye.",
        },
        "category": {
            "hi": "आप किस श्रेणी में आते हैं? (SC/ST/OBC/General/EWS)",
            "en": "What is your category? (SC/ST/OBC/General/EWS)",
            "hinglish": "Aapki category kya hai? (SC/ST/OBC/General/EWS)",
        },
        "annual_income": {
            "hi": "आपकी वार्षिक पारिवारिक आय लगभग कितनी है?",
            "en": "What is your approximate annual family income?",
            "hinglish": "Approx annual family income kitni hai?",
        },
    }

    field_questions = questions.get(missing_field, questions["life_event"])
    return field_questions.get(language, field_questions["en"])


def generate_no_schemes_response(language: str = "hi") -> str:
    """Generate response when no schemes match the user's profile.

    Honest and helpful — doesn't blame the user, suggests actionable alternatives.
    """
    responses = {
        "hi": (
            "मुझे खेद है, आपकी जानकारी के अनुसार फ़िलहाल कोई योजना उपलब्ध नहीं है।\n\n"
            "आप ये कर सकते हैं:\n"
            "• किसी और विषय में योजना देखें (जैसे: घर, स्वास्थ्य, रोजगार, पेंशन)\n"
            "• अगर कोई जानकारी बदलनी हो तो बताएं\n"
            "• /start दबाकर नया विषय चुनें\n\n"
            "आप क्या करना चाहेंगे?"
        ),
        "en": (
            "Unfortunately, we don't currently have schemes matching your profile "
            "for this category.\n\n"
            "You can:\n"
            "• Explore a different area (housing, health, employment, pension)\n"
            "• Update your details if something has changed\n"
            "• Send /start to begin a fresh search\n\n"
            "What would you like to do?"
        ),
        "hinglish": (
            "Abhi aapki profile ke hisaab se is category mein matching scheme nahi mili.\n\n"
            "Aap ye kar sakte hain:\n"
            "• Kisi aur area mein dekh sakte hain (housing, health, employment, pension)\n"
            "• Agar koi detail badalni ho toh batayiye\n"
            "• /start bhejkar fresh search shuru kariye\n\n"
            "Aap kya karna chahenge?"
        ),
    }
    return responses.get(language, responses["en"])


def generate_farewell_response(language: str = "hi") -> str:
    """Generate farewell response when the user ends the conversation."""
    farewells = {
        "hi": (
            "धन्यवाद! 🙏 आपसे बात करके अच्छा लगा।\n\n"
            "जब भी सरकारी योजनाओं की जानकारी चाहिए, /start भेजें।\n"
            "शुभकामनाएं! 😊"
        ),
        "en": (
            "Thank you for using Delhi Scheme Saathi! 🙏\n\n"
            "Whenever you need help with government schemes, just send /start.\n"
            "Take care! 😊"
        ),
        "hinglish": (
            "Delhi Scheme Saathi use karne ke liye shukriya! 🙏\n\n"
            "Jab bhi government schemes mein help chahiye ho, bas /start bhej dijiye.\n"
            "Take care! 😊"
        ),
    }
    return farewells.get(language, farewells["en"])


def generate_scheme_selection_response(language: str = "hi") -> str:
    """Generate response asking user to select a scheme."""
    responses = {
        "hi": "इनमें से कौन सी योजना के बारे में आप विस्तार से जानना चाहते हैं?",
        "en": "Which scheme would you like to know more about?",
        "hinglish": "Inmein se kis scheme ke baare mein detail chahiye?",
    }
    return responses.get(language, responses["en"])


def generate_field_reason_response(field: str, language: str = "hi") -> str:
    """Explain why a specific field matters and re-ask it."""
    reasons = {
        "life_event": {
            "hi": "आपकी स्थिति जानने से मैं सही योजनाएं ढूँढ सकता हूं। कृपया बताएं कि आपको किस तरह की सहायता चाहिए?",
            "en": "Knowing your situation helps me find the right schemes. What kind of assistance do you need?",
            "hinglish": "Aapki situation samajhne se main sahi schemes dhoondh sakta hoon. Batayiye, kis tarah ki madad chahiye?",
        },
        "age": {
            "hi": "उम्र से मैं सही पात्रता जाँच सकता हूं। कृपया आवेदक की उम्र बताएं।",
            "en": "Age helps me check the right eligibility rules. Please share the applicant's age.",
            "hinglish": "Age se main sahi eligibility check kar sakta hoon. Please applicant ki age batayiye.",
        },
        "category": {
            "hi": "श्रेणी से सही योजनाएं और पात्रता तय होती हैं। कृपया SC/ST/OBC/General/EWS बताएं।",
            "en": "Category affects eligibility for many schemes. Please share SC/ST/OBC/General/EWS.",
            "hinglish": "Category se kai schemes ki eligibility decide hoti hai. Please SC/ST/OBC/General/EWS batayiye.",
        },
        "annual_income": {
            "hi": "आय से मैं सही पात्रता और लाभ जाँच सकता हूं। कृपया अनुमानित वार्षिक आय बताएं।",
            "en": "Income helps me check the right eligibility and benefits. Please share the approximate annual income.",
            "hinglish": "Income se main sahi eligibility aur benefits check kar sakta hoon. Please approx annual income batayiye.",
        },
        "gender": {
            "hi": "कुछ योजनाएं लिंग के आधार पर अलग होती हैं। कृपया बताएं आवेदक पुरुष हैं या महिला।",
            "en": "Some schemes differ by gender. Please tell me whether the applicant is male or female.",
            "hinglish": "Kuch schemes gender ke hisaab se alag hoti hain. Please batayiye applicant male hai ya female.",
        },
    }
    field_reasons = reasons.get(field, reasons["life_event"])
    return field_reasons.get(language, field_reasons["en"])


def generate_field_help_response(field: str, language: str = "hi") -> str:
    """Explain how to answer a field question and re-ask it."""
    help_text = {
        "life_event": {
            "hi": "आप जिस मदद की तलाश कर रहे हैं, वही बताइए, जैसे: housing, widow pension, health treatment, education loan. आपको किस तरह की सहायता चाहिए?",
            "en": "Please tell me the kind of help you need, for example: housing, widow pension, health treatment, or education loan. What assistance are you looking for?",
            "hinglish": "Aapko kis type ki help chahiye woh batayiye, jaise housing, widow pension, health treatment ya education loan. Aap kis assistance ki talash mein hain?",
        },
        "age": {
            "hi": "कृपया पूरी उम्र सालों में बताएं, जैसे 24 या 45 years.",
            "en": "Please share the completed age in years, for example 24 or 45 years.",
            "hinglish": "Please completed age years mein batayiye, jaise 24 ya 45 years.",
        },
        "category": {
            "hi": "अगर पता हो तो इनमें से एक बताएं: SC, ST, OBC, General, EWS. अगर निश्चित न हों तो 'skip' भी लिख सकते हैं.",
            "en": "If you know it, please choose one: SC, ST, OBC, General, or EWS. If you are not sure, you can also say 'skip'.",
            "hinglish": "Agar pata ho to inmein se ek batayiye: SC, ST, OBC, General ya EWS. Agar sure nahi hain to 'skip' bhi bol sakte hain.",
        },
        "annual_income": {
            "hi": "अनुमानित वार्षिक पारिवारिक आय बताएं. अगर मासिक आय पता है, तो उसका 12 गुना बता सकते हैं, जैसे 50,000 monthly मतलब लगभग 6 लाख yearly.",
            "en": "Please share approximate annual family income. If you only know the monthly amount, you can multiply it by 12, for example 50,000 monthly is about 6 lakh yearly.",
            "hinglish": "Approx annual family income batayiye. Agar sirf monthly amount pata ho to uska 12 times bata sakte hain, jaise 50,000 monthly matlab roughly 6 lakh yearly.",
        },
        "gender": {
            "hi": "कृपया बताएं आवेदक male हैं या female. अगर योजना महिला-विशेष है, तो यह जानकारी जरूरी हो सकती है.",
            "en": "Please tell me whether the applicant is male or female. Some schemes are gender-specific, so this can matter.",
            "hinglish": "Please batayiye applicant male hai ya female. Kuch schemes gender-specific hoti hain, isliye yeh zaroori ho sakta hai.",
        },
    }
    field_help = help_text.get(field, help_text["life_event"])
    return field_help.get(language, field_help["en"])


def generate_application_guidance(
    scheme_name: str,
    application_url: str | None,
    offline_process: str | None,
    application_steps: list[str] | None = None,
    processing_time: str | None = None,
    helpline_phone: str | None = None,
    language: str = "hi",
) -> str:
    """Generate application guidance response."""
    if language == "hi":
        response = f"📝 {scheme_name} के लिए आवेदन:\n\n"
        if application_steps:
            response += "📋 आवेदन के चरण:\n"
            response += "\n".join(application_steps) + "\n\n"
        if application_url:
            response += f"🌐 ऑनलाइन आवेदन:\n{application_url}\n\n"
        if offline_process:
            response += f"🏛️ ऑफलाइन आवेदन:\n{offline_process}\n\n"
        if processing_time:
            response += f"⏱️ प्रक्रिया समय:\n{processing_time}\n\n"
        if helpline_phone:
            response += f"📞 संपर्क:\n{helpline_phone}\n\n"
        response += "क्या आपको दस्तावेजों की जानकारी चाहिए, या कोई और सवाल है?"
        return response

    if language == "hinglish":
        response = f"📝 {scheme_name} ke liye apply kaise karein:\n\n"
        if application_steps:
            response += "📋 Step-by-step process:\n"
            response += "\n".join(application_steps) + "\n\n"
        if application_url:
            response += f"🌐 Online apply:\n{application_url}\n\n"
        if offline_process:
            response += f"🏛️ Offline process:\n{offline_process}\n\n"
        if processing_time:
            response += f"⏱️ Processing time:\n{processing_time}\n\n"
        if helpline_phone:
            response += f"📞 Contact:\n{helpline_phone}\n\n"
        response += "Kya aapko documents mein help chahiye, ya koi aur sawaal hai?"
        return response

    response = f"📝 How to Apply for {scheme_name}:\n\n"
    if application_steps:
        response += "📋 Step-by-step process:\n"
        response += "\n".join(application_steps) + "\n\n"
    if application_url:
        response += f"🌐 Online:\n{application_url}\n\n"
    if offline_process:
        response += f"🏛️ Offline:\n{offline_process}\n\n"
    if processing_time:
        response += f"⏱️ Processing time:\n{processing_time}\n\n"
    if helpline_phone:
        response += f"📞 Contact:\n{helpline_phone}\n\n"
    response += "Would you like help with documents, or do you have any other questions?"
    return response
