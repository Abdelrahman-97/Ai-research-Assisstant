/* Lightweight i18n for Neura.
 * English is the source language (strings live in app.js). When Arabic is
 * selected we (a) set <html lang="ar" dir="rtl"> so the whole layout flips
 * right-to-left, and (b) translate the visible UI text via the dictionary below,
 * applied after each render. Code previews, generated results, and the analyst
 * chat are NOT translated (they carry the user's own content). */

window.NEURA_I18N = (function () {
  const DICT = {
    // Topbar / global
    "Log out": "تسجيل الخروج",
    // Auth
    "Welcome back": "مرحبًا بعودتك",
    "Log in to continue.": "سجّل الدخول للمتابعة.",
    "Create your account": "أنشئ حسابك",
    "Sign up to get started.": "سجّل لتبدأ.",
    "Email": "البريد الإلكتروني",
    "Password": "كلمة المرور",
    "Log in": "تسجيل الدخول",
    "Sign up": "إنشاء حساب",
    "No account?": "ليس لديك حساب؟",
    "Already have an account?": "لديك حساب بالفعل؟",
    "Forgot password?": "هل نسيت كلمة المرور؟",
    "Default scope (you can change it per job)": "النطاق الافتراضي (يمكن تغييره لكل مهمة)",
    "Thesis chapter": "فصل رسالة علمية",
    "Paper / study": "بحث / دراسة",
    // Forgot password
    "Reset your password": "إعادة تعيين كلمة المرور",
    "Enter your email and we'll send you a reset link.": "أدخل بريدك الإلكتروني وسنرسل لك رابط إعادة التعيين.",
    "Send reset link": "إرسال رابط إعادة التعيين",
    "← Back to sign in": "← العودة لتسجيل الدخول",
    // Dashboard
    "Your workspace": "مساحة عملك",
    "Start a new Results section, or continue a job.": "ابدأ قسم نتائج جديد، أو تابع مهمة.",
    "+ New Results section": "+ قسم نتائج جديد",
    "My jobs": "مهامي",
    "Files are kept 30 days after you accept the results.": "تُحفظ الملفات ٣٠ يومًا بعد قبولك للنتائج.",
    "No jobs yet. Start your first one.": "لا توجد مهام بعد. ابدأ أول مهمة.",
    "Verify your email.": "فعّل بريدك الإلكتروني.",
    "Resend": "إعادة الإرسال",
    "Delete my account and all data": "حذف حسابي وكل البيانات",
    "Results section": "قسم النتائج",
    // New task
    "← Back": "← رجوع",
    "New Results section": "قسم نتائج جديد",
    "What are you writing this for?": "لِمَ تكتب هذا؟",
    "Longer, detailed results chapter": "فصل نتائج مفصّل وأطول",
    "Concise results section": "قسم نتائج موجز",
    "Continue": "متابعة",
    // Run shell / stepper
    "← My jobs": "← مهامي",
    "Upload": "الرفع",
    "Price": "السعر",
    "Pay": "الدفع",
    "Plan": "الخطة",
    "Script": "الكود",
    "Run": "التشغيل",
    "Results": "النتائج",
    // Upload
    "Upload your study": "ارفع دراستك",
    "We validate the data and use it to price the job — this step is free.": "نتحقق من البيانات ونستخدمها لتسعير المهمة — هذه الخطوة مجانية.",
    "Protocol / methods": "البروتوكول / المنهجية",
    "Data file (Excel or CSV)": "ملف البيانات (Excel أو CSV)",
    "Upload & validate": "رفع وتحقق",
    // Estimate
    "Data looks good": "البيانات سليمة",
    "valid": "صالحة",
    "Rows": "الصفوف",
    "Columns": "الأعمدة",
    "Target word count for the Results section": "عدد الكلمات المستهدف لقسم النتائج",
    "Interaction with your analyst": "التفاعل مع محللك",
    "How much you can chat to refine the plan, re-run, or add analyses.": "مدى قدرتك على المحادثة لتحسين الخطة أو إعادة التشغيل أو إضافة تحاليل.",
    "Basic — a few messages, included": "أساسي — رسائل قليلة، مضمّنة",
    "Standard — comfortable back-and-forth (+75 EGP)": "قياسي — تفاعل مريح (+٧٥ ج.م)",
    "Pro — heavy iteration & multiple analyses (+200 EGP)": "احترافي — تفاعل مكثّف وتحاليل متعددة (+٢٠٠ ج.م)",
    "Expert consultation (optional)": "استشارة خبير (اختياري)",
    "Add a human statistician for extra confidence.": "أضف إحصائيًا بشريًا لمزيد من الثقة.",
    "None — the AI does the analysis": "بدون — الذكاء الاصطناعي يجري التحليل",
    "Expert review of the results (+500 EGP)": "مراجعة خبير للنتائج (+٥٠٠ ج.م)",
    "Full expert analysis by a statistician (+3000 EGP, longer turnaround)": "تحليل كامل بواسطة إحصائي (+٣٠٠٠ ج.م، وقت أطول)",
    "Get price": "احصل على السعر",
    // Pay
    "Your price": "سعرك",
    "Proceed to payment": "المتابعة للدفع",
    "Change word count": "تغيير عدد الكلمات",
    "After paying, this page updates automatically once the payment is confirmed.": "بعد الدفع، تُحدَّث هذه الصفحة تلقائيًا عند تأكيد الدفع.",
    // Start plan
    "Payment confirmed": "تم تأكيد الدفع",
    "paid": "مدفوع",
    "Ready to analyse. The AI will propose a statistical plan for you to approve.": "جاهز للتحليل. سيقترح الذكاء الاصطناعي خطة إحصائية لاعتمادها.",
    "Propose statistical plan": "اقترح خطة إحصائية",
    // Plan
    "Proposed plan — your approval needed": "الخطة المقترحة — بحاجة لموافقتك",
    "Test": "الاختبار",
    "Reasoning": "التبرير",
    "Variables (comma-separated)": "المتغيرات (مفصولة بفواصل)",
    "Approve & continue": "اعتماد ومتابعة",
    // Script
    "Plan approved": "تم اعتماد الخطة",
    "approved": "معتمد",
    "Choose the language; the AI writes the analysis script for you to preview.": "اختر اللغة؛ يكتب الذكاء الاصطناعي كود التحليل لمعاينته.",
    "Generate script": "توليد الكود",
    "Script preview": "معاينة الكود",
    "This runs in an isolated sandbox (no network). Review it, then run.": "يعمل هذا في بيئة معزولة (بدون إنترنت). راجعه ثم شغّله.",
    "Run analysis": "تشغيل التحليل",
    // Write results
    "Analysis complete": "اكتمل التحليل",
    "executed": "تم التنفيذ",
    "Output": "المخرجات",
    "Write Results section": "كتابة قسم النتائج",
    "Output format": "تنسيق المخرجات",
    "Language of the write-up": "لغة الكتابة",
    "Style": "النمط",
    "Preview a sample": "معاينة نموذج",
    "First figure number": "رقم أول شكل",
    "First table number": "رقم أول جدول",
    // Results
    "ready": "جاهز",
    "accepted": "مقبول",
    "Accept results": "قبول النتائج",
    // Busy
    "Queued — the analysis will start shortly…": "في قائمة الانتظار — سيبدأ التحليل قريبًا…",
    "Running the analysis in the sandbox…": "جارٍ تشغيل التحليل في البيئة المعزولة…",
    "Writing the Results section…": "جارٍ كتابة قسم النتائج…",
    // Assistant
    "Your analyst": "محللك",
    "Send": "إرسال",
    // Footer
    "Terms of Service": "شروط الخدمة",
    "Refund Policy": "سياسة الاسترداد",
    "Privacy Policy": "سياسة الخصوصية",
    "Support:": "الدعم:",
    "email": "البريد",
    "WhatsApp": "واتساب",
    // Workspace / dashboard
    "Research workspace": "مساحة العمل البحثية",
    "Choose an analysis to begin.": "اختر تحليلًا للبدء.",
    "About Neura": "عن Neura",
    "Delete account": "حذف الحساب",
    "Upload data → AI plan → full write-up (Word/PDF)": "ارفع البيانات ← خطة بالذكاء الاصطناعي ← تقرير كامل (Word/PDF)",
    "Pool studies · heterogeneity · bias · subgroups": "تجميع الدراسات · التباين · التحيّز · المجموعات الفرعية",
    "Power & sample-size for every common design": "القوة وحجم العينة لكل التصاميم الشائعة",
    "Sensitivity · specificity · PPV/NPV · LRs": "الحساسية · النوعية · القيم التنبؤية · نِسب الأرجحية",
    // Tool inputs — shared
    "Continue to price": "المتابعة إلى السعر",
    "Model": "النموذج",
    "Random effects": "التأثيرات العشوائية",
    "Fixed effect": "التأثير الثابت",
    "Effect measure": "مقياس الأثر",
    "Studies — one per line": "الدراسات — سطر لكل دراسة",
    "Studies — one per line, comma-separated": "الدراسات — سطر لكل دراسة، مفصولة بفواصل",
    // Meta-analysis input modes
    "How do you want to enter your studies?": "كيف تريد إدخال دراساتك؟",
    "Upload a spreadsheet (Excel/CSV) — recommended": "ارفع ملف جدول (Excel/CSV) — مُستحسن",
    "Enter studies one by one (guided form)": "أدخل الدراسات واحدة تلو الأخرى (نموذج موجّه)",
    "Paste a table (advanced)": "الصق جدولًا (متقدّم)",
    "⬇ Download template (.csv)": "⬇ تنزيل القالب (.csv)",
    "Check my file": "تحقّق من ملفي",
    "+ Add study": "+ إضافة دراسة",
    "Analysis options": "خيارات التحليل",
    "Write-up for": "الكتابة من أجل",
    "Document type": "نوع المستند",
    "Language": "اللغة",
    "Reference / format style": "نمط المراجع / التنسيق",
    "Thesis chapter": "فصل من رسالة علمية",
    "Paper / study": "بحث / دراسة",
    "Standard": "قياسي",
    "Two-column": "عمودان",
    "Pre–post correlation (r)": "معامل الارتباط قبل/بعد (r)",
    "Continue": "متابعة",
    "🔬 Audited analyses selected": "🔬 تحاليل موثّقة مختارة",
    "no custom code": "بدون أكواد مخصّصة",
    "audited engines": "محرّكات موثّقة",
    "Between-study variance (τ²)": "التباين بين الدراسات (τ²)",
    "Fill in one study at a time. Add a row for each study (minimum 2).":
      "املأ دراسة واحدة في كل مرة. أضف صفًّا لكل دراسة (بحدّ أدنى دراستان).",
    "What are you comparing?": "ما الذي تقارنه؟",
    "Significance (alpha)": "مستوى الدلالة (ألفا)",
    "Power": "القوة الإحصائية",
    "Expected drop-out (optional)": "نسبة التسرّب المتوقعة (اختياري)",
    "True positives (TP)": "الإيجابيات الصحيحة (TP)",
    "False positives (FP)": "الإيجابيات الكاذبة (FP)",
    "False negatives (FN)": "السلبيات الكاذبة (FN)",
    "True negatives (TN)": "السلبيات الصحيحة (TN)",
    "A complete, cited report you can download as Word and PDF.": "تقرير كامل وموثّق يمكنك تنزيله بصيغتي Word وPDF.",
    "Edit inputs": "تعديل المدخلات",
    // Help tips (plain text)
    "💡 Describe your design, groups, and the outcomes you want compared. The clearer this is, the better the AI's proposed analysis. Arabic is supported.":
      "💡 صف تصميم دراستك ومجموعاتك والنتائج التي تريد مقارنتها. كلما كان الوصف أوضح، كانت خطة التحليل المقترحة أفضل. اللغة العربية مدعومة.",
    "💡 One row per participant, one column per variable, with a header row. Arabic column names are fine. Nothing is charged until you see and approve the price.":
      "💡 صف واحد لكل مشارك، وعمود لكل متغير، مع صف عناوين. أسماء الأعمدة بالعربية مقبولة. لا يُخصم أي مبلغ حتى ترى السعر وتوافق عليه.",
    "💡 This is the exact code that will analyse your data — shown for full transparency. You don't need to understand it; just click \"Run analysis\" to execute it safely.":
      "💡 هذا هو الكود الفعلي الذي سيحلّل بياناتك — معروض لأقصى درجات الشفافية. لست بحاجة لفهمه؛ فقط اضغط «تشغيل التحليل» لتنفيذه بأمان.",
    "💡 Want changes first? Use \"Your analyst\" chat below to refine wording, re-run, or add analyses before you accept. Download the Word file to edit it yourself.":
      "💡 تريد تعديلات أولًا؟ استخدم محادثة «محللك» بالأسفل لتحسين الصياغة أو إعادة التشغيل أو إضافة تحاليل قبل القبول. ونزّل ملف Word لتعدّله بنفسك.",
  };

  // Placeholders (translated as attributes, not text nodes).
  const PLACEHOLDERS = {
    "you@example.com": "you@example.com",
    "••••••••": "••••••••",
    "Paste the methods / analysis plan of your study...": "الصق منهجية / خطة تحليل دراستك...",
    "Message your analyst…": "راسل محللك…",
    "You've used all your assistant messages for this job.": "لقد استخدمت كل رسائل المحلل لهذه المهمة.",
  };

  // Containers whose text must NOT be translated (user content / code).
  const SKIP = new Set(["PRE", "CODE", "SCRIPT", "STYLE", "TEXTAREA", "INPUT"]);
  function inSkip(node) {
    let el = node.parentElement;
    while (el) {
      if (SKIP.has(el.tagName)) return true;
      if (el.classList && (el.classList.contains("md") || el.classList.contains("asst-log"))) return true;
      el = el.parentElement;
    }
    return false;
  }

  function translateDynamic(s) {
    let m;
    if ((m = s.match(/^(\d+) messages? left$/)))
      return `${m[1]} رسالة متبقية`;
    if ((m = s.match(/^Estimated (.+?) statistical test\(s\) · (.+?) words\.$/)))
      return `عدد التحاليل المقدَّر: ${m[1]} · ${m[2]} كلمة.`;
    return null;
  }

  function getLang() { try { return localStorage.getItem("neura_lang") || "en"; } catch (e) { return "en"; } }
  function setLang(l) { try { localStorage.setItem("neura_lang", l); } catch (e) {} }

  function apply() {
    const lang = getLang();
    document.documentElement.setAttribute("lang", lang);
    document.documentElement.setAttribute("dir", lang === "ar" ? "rtl" : "ltr");
    if (lang !== "ar") return;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const n of nodes) {
      if (inSkip(n)) continue;
      const key = n.nodeValue.trim();
      if (!key) continue;
      const val = DICT[key] || translateDynamic(key);
      if (val) n.nodeValue = n.nodeValue.replace(key, val);
    }
    document.querySelectorAll("[placeholder]").forEach((el) => {
      const k = (el.getAttribute("placeholder") || "").trim();
      if (PLACEHOLDERS[k]) el.setAttribute("placeholder", PLACEHOLDERS[k]);
    });
  }

  return { apply, getLang, setLang };
})();
