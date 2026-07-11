"""Generate data/knowledge/*.json — structured student KB + service walkthroughs."""
import json
import os

def t(zh, en, ja):
    return {"zh-TW": zh, "en": en, "ja": ja}

def sec(heading_zh, heading_en, heading_ja, body_zh, body_en, body_ja, source_ids=None):
    return {
        "heading": t(heading_zh, heading_en, heading_ja),
        "body": t(body_zh, body_en, body_ja),
        "source_ids": source_ids or [],
    }

SOURCES = [
    {
        "id": "src_isa",
        "tier": "official",
        "name": t("出入國在留管理廳", "Immigration Services Agency", "出入国在留管理庁"),
        "url": "https://www.moj.go.jp/isa/index.html",
        "domain": "moj.go.jp",
        "trust_score": 10,
    },
    {
        "id": "src_soumu_jumin",
        "tier": "official",
        "name": t("總務省｜住民登錄", "MIC | Resident registration", "総務省｜住民登録"),
        "url": "https://www.soumu.go.jp/menu_seiho/seiho/seido/jumin/ju_min.html",
        "domain": "soumu.go.jp",
        "trust_score": 10,
    },
    {
        "id": "src_mhlw_nhi",
        "tier": "official",
        "name": t("厚生勞動省｜國民健康保險", "MHLW | National Health Insurance", "厚生労働省｜国民健康保険"),
        "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryouhoken/iryouhoken15/index.html",
        "domain": "mhlw.go.jp",
        "trust_score": 10,
    },
    {
        "id": "src_jp_bank",
        "tier": "official",
        "name": t("ゆうちょ銀行", "Japan Post Bank", "ゆうちょ銀行"),
        "url": "https://www.jp-bank.japanpost.jp/bank/en/ijpbnksttopmn/index.html",
        "domain": "jp-bank.japanpost.jp",
        "trust_score": 10,
    },
    {
        "id": "src_nenkin",
        "tier": "official",
        "name": t("日本年金機構", "Japan Pension Service", "日本年金機構"),
        "url": "https://www.nenkin.go.jp/",
        "domain": "nenkin.go.jp",
        "trust_score": 10,
    },
    {
        "id": "src_mynumber",
        "tier": "official",
        "name": t("內閣府｜My Number", "Cabinet Office | My Number", "内閣府｜マイナンバー"),
        "url": "https://www.kojinbango-card.go.jp/en/",
        "domain": "kojinbango-card.go.jp",
        "trust_score": 10,
    },
    {
        "id": "src_soumu_mobile",
        "tier": "official",
        "name": t("總務省｜手機契約", "MIC | Mobile contracts", "総務省｜携帯契約"),
        "url": "https://www.soumu.go.jp/menu_seiho/seiho/seido/joho_tsusin/mobilenet/kaigai.html",
        "domain": "soumu.go.jp",
        "trust_score": 10,
    },
    {
        "id": "src_jasso",
        "tier": "semi_official",
        "name": t("JASSO 留學生支援", "JASSO Study in Japan", "JASSO 留学生支援"),
        "url": "https://www.studyinjapan.go.jp/en/",
        "domain": "studyinjapan.go.jp",
        "trust_score": 9,
    },
]

ARTICLES = [
    {
        "id": "kb_task_address",
        "task_ids": ["task_address"],
        "priority": 10,
        "title": t("住民登錄：留學生必懂重點", "Resident registration essentials", "住民登録：留学生の要点"),
        "summary": t(
            "抵達日本後14天內，必須到居住地的區役所辦理住民登錄。這是健保、手機、銀行開戶的共同前提。",
            "Within 14 days of finding a residence, register at your ward office. Required for NHI, phone, and bank.",
            "住居確定後14日以内に区役所で住民登録。健保・携帯・銀行の前提手続き。",
        ),
        "sections": [
            sec(
                "為什麼一定要做", "Why it matters", "なぜ必要か",
                "沒有住民登錄就無法取得正式的居住地址證明（住民票），而多數行政與商業服務都會要求這份文件。",
                "Without registration you cannot get a resident certificate (juminhyo), required by most services.",
                "住民票がないと携帯・銀行・保険など多くの手続きができません。",
                ["src_soumu_jumin"],
            ),
            sec(
                "常見錯誤", "Common mistakes", "よくある間違い",
                "超過14天、帶錯地址證明、忘記在留卡。若住在宿舍，請向學校索取「居住證明」再前往區役所。",
                "Missing the 14-day deadline, wrong address proof, forgetting residence card. Dorm residents need school housing proof.",
                "14日超過、住所証明の不備、在留カード忘れ。寮生は学校の居住証明が必要な場合があります。",
                ["src_soumu_jumin"],
            ),
        ],
        "source_ids": ["src_soumu_jumin", "src_isa"],
    },
    {
        "id": "kb_task_bank",
        "task_ids": ["task_bank"],
        "priority": 10,
        "title": t("銀行開戶：留學生路線", "Bank account for students", "銀行口座：留学生向け"),
        "summary": t(
            "多數留學生首選ゆうちょ銀行（郵政銀行），因對外國人相對友善。開戶前請先完成住民登錄與手機門號。",
            "Many students start with Japan Post Bank. Complete resident registration and a phone number first.",
            "多くの留学生はゆうちょ銀行が初めやすい。住民登録と携帯番号を先に済ませてください。",
        ),
        "sections": [
            sec(
                "開戶順序", "Correct order", "手続きの順番",
                "住民登錄 → 手機門號 → 銀行開戶。這個順序能避免櫃台以「資料不足」退回。",
                "Register address → get phone → open bank. This order avoids rejections at the counter.",
                "住民登録→携帯→銀行の順が基本。書類不足で断られるのを防げます。",
                ["src_jp_bank"],
            ),
        ],
        "source_ids": ["src_jp_bank"],
    },
    {
        "id": "kb_task_phone",
        "task_ids": ["task_phone"],
        "priority": 9,
        "title": t("手機門號：外國人契約要點", "Mobile contracts for foreigners", "携帯契約の要点"),
        "summary": t(
            "日本多數電信方案需要住民票與在留卡。短期可先使用機場 SIM，長期建議到門市辦理月租方案。",
            "Most carriers need juminhyo and residence card. Airport SIM for short term; visit a store for monthly plans.",
            "多くのキャリアは住民票と在留カードが必要。短期は空港SIM、長期は店舗契約がおすすめ。",
        ),
        "sections": [],
        "source_ids": ["src_soumu_mobile"],
    },
    {
        "id": "kb_task_pension",
        "task_ids": ["task_pension"],
        "priority": 9,
        "title": t("國民年金學生免除", "Student pension exemption", "国民年金の学生納付特例"),
        "summary": t(
            "在學中的留學生可申請「学生納付特例」暫緩繳費。需向年金事務所提交申請書與學生證明。",
            "Students can apply for payment exemption at the pension office with student proof.",
            "在学中は「学生納付特例」で保険料納付を猶予できます。年金事務所へ申請。",
        ),
        "sections": [],
        "source_ids": ["src_nenkin"],
    },
]

def guide_step(title_zh, title_en, title_ja, inst_zh, inst_en, inst_ja, checklist=None, tip_zh="", tip_en="", tip_ja="", url=""):
    return {
        "title": t(title_zh, title_en, title_ja),
        "instruction": t(inst_zh, inst_en, inst_ja),
        "checklist": checklist or [],
        "tip": t(tip_zh, tip_en, tip_ja) if tip_zh else {},
        "external_url": url,
    }

def chk(zh, en, ja):
    return {"text": t(zh, en, ja)}

SERVICE_GUIDES = [
    {
        "id": "guide_juminhyo",
        "task_ids": ["task_address"],
        "priority": 10,
        "service_key": "ward_office",
        "title": t("區役所住民登錄｜逐步引導", "Ward office registration walkthrough", "区役所・住民登録ガイド"),
        "description": t(
            "帶著文件前往區役所，完成住民登錄並領取住民票。",
            "Visit your ward office with documents to register and get your resident certificate.",
            "必要書類を持って区役所で住民登録と住民票取得を行います。",
        ),
        "estimated_min": 45,
        "source_ids": ["src_soumu_jumin"],
        "steps": [
            guide_step(
                "出發前確認", "Before you go", "出発前の確認",
                "確認今天是否為平日、區役所是否營業。準備護照、在留卡、租房合約或宿舍居住證明。",
                "Check weekday hours. Prepare passport, residence card, lease or dorm proof.",
                "平日・開庁時間を確認。パスポート・在留カード・賃貸契約または寮証明を準備。",
                [chk("護照", "Passport", "パスポート"), chk("在留卡", "Residence card", "在留カード"), chk("住址證明", "Address proof", "住所証明")],
                "建議事先查好區役所窗口營業時間，避免白跑一趟。",
                "Check ward office hours online first.",
                "区役所の受付時間を事前に確認しましょう。",
            ),
            guide_step(
                "填寫申請表", "Fill the form", "申請書の記入",
                "在窗口或自助區索取「住民異動届」。用日文或英文填寫姓名、生日、國籍、新地址。不確定可請工作人員協助。",
                "Get the moving-in notification form. Fill name, birth date, nationality, new address. Ask staff if unsure.",
                "「住民異動届」を取得し、氏名・生年月日・国籍・新住所を記入。不明点は職員に相談。",
                [chk("姓名與在留卡一致", "Name matches residence card", "在留カードと氏名一致"), chk("地址正確", "Address is correct", "住所が正確")],
            ),
            guide_step(
                "提交並領取住民票", "Submit and get juminhyo", "提出と住民票",
                "提交表格與證件。可同時申請住民票（建議2〜3份），之後辦手機與銀行會用到。",
                "Submit form and ID. Request 2–3 copies of your resident certificate for phone and bank.",
                "提出後、住民票を2〜3通取得（携帯・銀行で必要）。",
                [chk("已拿到住民票", "Received juminhyo", "住民票を受領")],
                "住民票有效期通常為3個月，請留意各機構要求。",
                "Juminhyo is usually valid for 3 months per copy.",
                "住民票の発行日から3か月が目安です。",
            ),
        ],
    },
    {
        "id": "guide_yuucho_bank",
        "task_ids": ["task_bank"],
        "priority": 10,
        "service_key": "jp_bank",
        "title": t("ゆうちょ銀行開戶｜逐步引導", "Japan Post Bank account walkthrough", "ゆうちょ銀行・口座開設ガイド"),
        "description": t(
            "在郵局銀行窗口開設留學生常用的銀行帳戶。",
            "Open a student-friendly account at Japan Post Bank.",
            "ゆうちょ銀行で口座を開設します。",
        ),
        "estimated_min": 60,
        "source_ids": ["src_jp_bank"],
        "steps": [
            guide_step(
                "確認前置條件", "Prerequisites", "前提の確認",
                "請確認已完成住民登錄並持有日本手機號碼。這兩項是開戶時最常要求的資料。",
                "Confirm resident registration and a Japanese phone number — commonly required.",
                "住民登録と日本の携帯番号があるか確認。",
                [chk("住民票", "Juminhyo", "住民票"), chk("手機號碼", "Phone number", "携帯番号")],
                url="https://www.jp-bank.japanpost.jp/bank/en/ijpbnksttopmn/index.html",
            ),
            guide_step(
                "前往郵局銀行窗口", "Visit the counter", "窓口へ",
                "尋找標示「銀行業務」的窗口。告知店員要開設普通預金帳戶（普通預金口座）。",
                "Find the banking counter. Ask to open a regular savings account (futsu yokin).",
                "銀行窓口で「普通預金口座の開設」を伝える。",
                [chk("護照", "Passport", "パスポート"), chk("在留卡", "Residence card", "在留カード")],
            ),
            guide_step(
                "領取通帳與卡片", "Receive passbook/card", "通帳・カード受取",
                "完成後會拿到通帳（存摺）或現金卡。記下帳號，學費與房租轉帳會用到。",
                "You receive a passbook or cash card. Save your account number for tuition and rent.",
                "通帳またはキャッシュカードを受け取り、口座番号を控える。",
                [chk("已記下帳號", "Account number saved", "口座番号を控えた")],
            ),
        ],
    },
    {
        "id": "guide_mobile_contract",
        "task_ids": ["task_phone"],
        "priority": 9,
        "service_key": "mobile_carrier",
        "title": t("辦理日本門號｜逐步引導", "Japanese mobile contract walkthrough", "携帯契約ガイド"),
        "description": t(
            "在門市或線上官方管道辦理可長期使用的 SIM / 月租方案。",
            "Get a long-term SIM or monthly plan at a store or official online channel.",
            "店舗または公式オンラインで長期利用の携帯契約を行います。",
        ),
        "estimated_min": 40,
        "source_ids": ["src_soumu_mobile"],
        "steps": [
            guide_step(
                "選擇方案類型", "Choose plan type", "プランの選択",
                "留學生常見選擇：實體門市月租、或 SIM 自由契約（如 ahamo/linemo 等官方線上方案）。先比較流量與合約期。",
                "Compare monthly store plans vs online MVNO options. Check data and contract length.",
                "店舗の月額プランかオンラインSIMかを比較。データ量と契約期間を確認。",
            ),
            guide_step(
                "準備文件", "Prepare documents", "書類準備",
                "通常需要：護照、在留卡、住民票（或記載地址的證明）、信用卡或銀行帳戶。",
                "Usually need: passport, residence card, juminhyo, credit card or bank account.",
                "パスポート・在留カード・住民票・クレジットカードまたは銀行口座。",
                [chk("護照與在留卡", "Passport & residence card", "パスポートと在留カード"), chk("住民票", "Juminhyo", "住民票")],
            ),
            guide_step(
                "開通並測試", "Activate and test", "開通とテスト",
                "開通後撥打測試電話、確認上網。保留契約書與重要條款頁面。",
                "Test calls and mobile data. Keep your contract documents.",
                "通話とデータ通信をテスト。契約書を保管。",
                [chk("可正常通話", "Calls work", "通話OK"), chk("可正常上網", "Data works", "データOK")],
            ),
        ],
    },
    {
        "id": "guide_nenkin_exemption",
        "task_ids": ["task_pension"],
        "priority": 9,
        "service_key": "nenkin",
        "title": t("國民年金學生免除｜逐步引導", "Pension student exemption walkthrough", "年金学生納付特例ガイド"),
        "description": t(
            "向年金事務所申請在學期間的保險費納付猶予。",
            "Apply for student payment exemption at the pension office.",
            "年金事務所で学生納付特例を申請します。",
        ),
        "estimated_min": 30,
        "source_ids": ["src_nenkin"],
        "steps": [
            guide_step(
                "確認收到年金手冊", "Pension handbook", "年金手帳の確認",
                "完成住民登錄後，通常會收到國民年金加入通知與手冊。若未收到請向區役所或年金事務所確認。",
                "After resident registration you should receive pension enrollment notice. Ask ward/pension office if missing.",
                "住民登録後に加入通知が届きます。未着なら区役所か年金事務所へ。",
            ),
            guide_step(
                "填寫學生納付特例申請", "Fill exemption form", "申請書の記入",
                "在年金事務所或官網下載「学生納付特例申請書」。附上學校出具的在学證明。",
                "Get the student exemption form at the pension office or official site. Attach student certificate from school.",
                "「学生納付特例申請書」に学校の在学証明を添付。",
                [chk("在学證明", "Student certificate", "在学証明"), chk("年金手冊", "Pension handbook", "年金手帳")],
                url="https://www.nenkin.go.jp/service/kokunai/gakusei/gakusei.html",
            ),
            guide_step(
                "提交申請", "Submit", "提出",
                "可郵寄或親自提交。核准後在學期間可暫緩繳費，但需在狀況變更時重新申請。",
                "Submit by mail or in person. Renew if your student status changes.",
                "郵送または窓口で提出。在学状況が変わったら再申請。",
            ),
        ],
    },
]

base = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge")
os.makedirs(base, exist_ok=True)

for name, data in [
    ("sources.json", {"version": "1.0", "sources": SOURCES}),
    ("articles.json", {"version": "1.0", "articles": ARTICLES}),
    ("service_guides.json", {"version": "1.0", "guides": SERVICE_GUIDES}),
]:
    path = os.path.join(base, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {path}")
