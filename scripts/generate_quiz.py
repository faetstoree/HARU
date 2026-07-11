"""Generate data/quiz_questions.json — 4-choice diagnostic questions."""
import json
import os

def t(zh, en, ja):
    return {"zh-TW": zh, "en": en, "ja": ja}

def ch(id_, label_zh, label_en, label_ja, recommendation_zh="", recommendation_en="", recommendation_ja="", suggest_task=None):
    c = {"id": id_, "label": t(label_zh, label_en, label_ja)}
    if recommendation_zh:
        c["recommendation"] = t(recommendation_zh, recommendation_en, recommendation_ja)
    if suggest_task:
        c["suggest_task"] = suggest_task
    return c

QUESTIONS = [
    {
        "id": "q_residence_card",
        "task_ids": ["task_immigration"],
        "priority": 10,
        "skip_if_task_completed": "task_immigration",
        "prompt": t(
            "你是否已經拿到在留卡？",
            "Do you already have your residence card?",
            "在留カードはもう受け取りましたか？",
        ),
        "choices": [
            ch("a", "是，已在機場領取", "Yes, at the airport", "はい、空港で受け取った", "很好，請妥善保管在留卡，後續手續都需要。", "Keep it safe — you'll need it for all procedures.", "大切に保管してください。", "task_move_in"),
            ch("b", "還沒有", "Not yet", "まだ", "請盡快到區役所或入管辦理在留卡相關手續。", "Visit ward office or immigration soon.", "早めに区役所または入管へ。", "task_immigration"),
            ch("c", "不確定", "Not sure", "わからない", "請檢查護照夾或學校是否代為保管通知。", "Check your passport folder or ask your school.", "パスポートケースや学校に確認を。", None),
            ch("d", "弄丟了", "Lost it", "紛失した", "請立即向入管或警察報案並申請再發行。", "Report to immigration/police immediately.", "入管または警察へ届出を。", "task_immigration"),
        ],
    },
    {
        "id": "q_juminhyo",
        "task_ids": ["task_ward_office"],
        "priority": 12,
        "skip_if_task_completed": "task_ward_office",
        "prompt": t(
            "住民登錄（地址登記）的狀態？",
            "Status of resident registration?",
            "住民登録の状況は？",
        ),
        "choices": [
            ch("a", "已完成", "Completed", "完了", "下一步可辦理健保與手機門號。", "Next: health insurance and phone.", "次は健保と携帯契約。", "task_phone"),
            ch("b", "還沒，有固定地址了", "Not yet, but I have an address", "まだ、住所はある", "請盡快帶文件到區役所辦理。", "Visit ward office with documents soon.", "書類を持って区役所へ。", "task_ward_office"),
            ch("c", "地址還不確定", "Address not fixed yet", "住所が未定", "先確定住所或宿舍證明，再辦住民登錄。", "Confirm housing first.", "住居を確定してから。", "task_move_in"),
            ch("d", "不知道什麼是住民登錄", "Don't know what it is", "住民登録がわからない", "這是日本地址登記，建議使用 Haru 的「住民登錄操作引導」。", "Use Haru's resident registration walkthrough.", "操作ガイドをご利用ください。", "task_ward_office"),
        ],
    },
    {
        "id": "q_phone",
        "task_ids": ["task_phone"],
        "priority": 9,
        "skip_if_task_completed": "task_phone",
        "prompt": t(
            "日本手機門號的狀況？",
            "Japanese mobile phone status?",
            "日本の携帯電話の状況は？",
        ),
        "choices": [
            ch("a", "已有日本門號", "Have Japanese number", "日本の番号あり", "可以進行銀行開戶了。", "You can open a bank account.", "銀行口座開設が可能です。", "task_bank"),
            ch("b", "只有旅遊 SIM", "Tourist SIM only", "観光用SIMのみ", "長期建議辦理正式月租方案。", "Get a monthly plan for long stay.", "長期なら月額契約を。", "task_phone"),
            ch("c", "還沒有", "None yet", "まだない", "完成住民登錄後較容易辦理。", "Easier after resident registration.", "住民登録後がおすすめ。", "task_phone"),
            ch("d", "不清楚差別", "Don't know the difference", "違いがわからない", "可看 Haru 的「辦理門號逐步引導」。", "See the mobile walkthrough in Haru.", "携帯ガイドを参照。", "task_phone"),
        ],
    },
    {
        "id": "q_bank",
        "task_ids": ["task_bank"],
        "priority": 9,
        "skip_if_task_completed": "task_bank",
        "prompt": t(
            "銀行帳戶開設狀況？",
            "Bank account status?",
            "銀行口座の状況は？",
        ),
        "choices": [
            ch("a", "已開戶", "Opened", "開設済み", "很好，可設定學費與房租轉帳。", "Set up tuition/rent transfers.", "学費・家賃の振込設定を。", None),
            ch("b", "準備去開", "Planning to open", "開設予定", "確認已帶住民票、在留卡、手機號碼。", "Bring juminhyo, residence card, phone number.", "住民票・在留カード・携帯番号を。", "task_bank"),
            ch("c", "被銀行拒絕", "Was rejected", "断られた", "常見原因是缺手機號或住民票，或試ゆうちょ銀行。", "Often missing phone/juminhyo; try Japan Post Bank.", "携帯・住民票不足が多い。", "task_bank"),
            ch("d", "還沒開始", "Not started", "まだ", "需先完成住民登錄與門號。", "Complete registration and phone first.", "住民登録と携帯を先に。", "task_ward_office"),
        ],
    },
    {
        "id": "q_insurance",
        "task_ids": ["task_ward_office"],
        "priority": 8,
        "skip_if_task_completed": "task_ward_office",
        "prompt": t(
            "國民健康保險加入了嗎？",
            "Enrolled in National Health Insurance?",
            "国民健康保険に加入しましたか？",
        ),
        "choices": [
            ch("a", "已加入", "Yes", "はい", "就醫時請攜帶保險證。", "Bring insurance card when visiting clinics.", "診察時は保険証を。", None),
            ch("b", "住民登錄時應該辦了", "Did it at ward office", "区役所で一緒に", "確認是否已收到保險證。", "Check if you received the card.", "保険証の受け取りを確認。", None),
            ch("c", "還沒", "Not yet", "まだ", "通常與住民登錄一起在區役所辦理。", "Usually done with resident registration.", "住民登録と同時が一般的。", "task_ward_office"),
            ch("d", "不清楚", "Not sure", "わからない", "可帶在留卡到區役所確認。", "Ask ward office with residence card.", "区役所で確認を。", "task_ward_office"),
        ],
    },
    {
        "id": "q_part_time",
        "task_ids": ["task_work_permit"],
        "priority": 7,
        "prompt": t(
            "你打算在日本打工嗎？",
            "Planning to work part-time in Japan?",
            "日本でアルバイトする予定は？",
        ),
        "choices": [
            ch("a", "是，需要許可", "Yes, need permit", "はい、許可が必要", "請申請「資格外活動許可」。", "Apply for work permission.", "資格外活動許可を申請。", "task_work_permit"),
            ch("b", "否", "No", "いいえ", "可專注語言學校課業。", "Focus on language school.", "語学学校に専念。", None),
            ch("c", "之後再說", "Maybe later", "後で考える", "需要時再申請即可，但需預留審查時間。", "Apply when needed; allow processing time.", "必要時に申請、時間に余裕を。", "task_work_permit"),
            ch("d", "已在打工", "Already working", "もう働いている", "請確認是否已有合法許可，避免違法打工。", "Ensure you have legal permission.", "許可の有無を必ず確認。", "task_work_permit"),
        ],
    },
    {
        "id": "q_cash",
        "task_ids": ["task_immigration", "task_funds_prep"],
        "priority": 6,
        "skip_if_task_completed": "task_immigration",
        "prompt": t(
            "日圓現金準備得如何？",
            "How is your yen cash situation?",
            "円の現金は足りていますか？",
        ),
        "choices": [
            ch("a", "足夠一週以上", "Enough for a week+", "1週間以上ある", "可專注辦理行政手續。", "Focus on admin tasks.", "手続きに集中できます。", None),
            ch("b", "只夠幾天", "Only a few days", "数日分", "建議去銀行或兌換所補充現金。", "Top up cash at bank or exchange.", "銀行・両替で補充を。", "task_immigration"),
            ch("c", "幾乎沒有", "Almost none", "ほとんどない", "請優先換匯，否則交通與吃飯會受阻。", "Exchange money first.", "最優先で両替を。", "task_immigration"),
            ch("d", "都用卡", "Cards only", "カードのみ", "日本仍有許多場合只收現金，建議準備一些。", "Japan still uses cash often.", "現金も用意を。", "task_immigration"),
        ],
    },
]

out = os.path.join(os.path.dirname(__file__), "..", "data", "quiz_questions.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"version": "2.0", "max_questions": 6, "questions": QUESTIONS}, f, ensure_ascii=False, indent=2)
print(f"Wrote {len(QUESTIONS)} quiz questions")
