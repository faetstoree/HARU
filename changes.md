# HARU 変更履歴

---

## 一、AI 個人化ロードマップ

### 新規追加：`roadmap_ai_engine.py`
- `build_ai_roadmap_prompt()` — 学生の完全なプロフィール＋全タスク一覧から Gemini 用プロンプトを生成
- `generate_ai_roadmap()` — Gemini を呼び出し、`mission`・`agent_greeting`・`goal_summary`・`priority_message`・各タスクの個人化 `summary`/`steps`/`tips` を含む JSON overlay を返す
- `merge_ai_overlay_into_roadmap()` — AI overlay を静的ロードマップに統合し、`ai_personalization` トップレベルフィールドを付加

### `models.py`
- `ai_roadmap` フィールド追加（AI overlay JSON のキャッシュ）
- `ai_roadmap_lang` フィールド追加（言語切替時に再生成）
- `permit_obtained` フィールド追加（資格外活動許可の取得状況）

### `main.py`
- DB migration で `ai_roadmap`・`ai_roadmap_lang`・`permit_obtained` を自動追加
- `/api/user/init`：オンボーディング後すぐに AI 個人化ロードマップを生成し、DB にキャッシュして返却
- `/api/user/profile`：プロフィール更新後にキャッシュを破棄し、AI 再生成を実行
- `/api/roadmap`：ロードマップ取得時にキャッシュ済み AI overlay を統合
- `_apply_school_info_to_user` / `_school_info_from_user`：`permit_obtained` の読み書きを追加
- `generate_agent_decision()`：`get_genai_client()` に切り替え（API key があれば AI、なければ rule-based にフォールバック）。完全な try/except による降格保護を追加

### `agent_engine.py`
- `should_use_llm_for_agent()` を常に `True` を返すよう変更。ホーム画面の agent card がデフォルトで AI を使用

### `static/js/main.js`（AI 関連）
- `fetchAgentDecision` の `force_llm` を常に `true` に変更
- `applyMissionFromRoadmap()` が `ai_personalization.priority_message` と `agent_greeting` を優先表示
- `updateStatusHero()` がタイトル下に `ai_personalization.mission` を表示
- `renderTaskDetail()` が `task.ai_steps` を表示
- `fetchRoadmap()` と `submitOnboard()` はロードマップ受信後に mission を更新

### `templates/index.html`
- `<p id="statusHeroMission">` を追加（AI mission statement の表示領域）

### `static/css/haru-theme.css`
- `.status-hero-mission` — mission テキストのスタイル
- `.ai-steps-label`・`.ai-steps-list` — task detail の AI ステップブロックのスタイル

---

## 二、バグ修正

### 修正 1：ロードマップの Tab 切替が強制的に元に戻る
**根本原因**：`renderRoadmap()` が毎回 `selectedPhaseId` を上書きし、`scrollToCurrentFocus()` が無条件に現在のタスクへスクロールしていた。

**対応（`static/js/main.js`）**：
- `_suppressFocusScroll` フラグを追加
- Tab の onclick は `renderRoadmap()` を呼ばず、`selectedPhaseId` の設定・active クラス更新・Canvas スクロールの 3 つのみ実行
- Tab クリック時に `_suppressFocusScroll = true` をセットし、直後の非同期 `renderRoadmap` が `scrollToCurrentFocus` を実行しないよう制御
- `renderRoadmap` の phase 初期化は `selectedPhaseId` が null の場合のみ自動計算
- `ensureTaskSelected` は `selectedPhaseId` が未設定の場合のみ呼び出し

### 修正 2：資格外活動許可のオンボーディングフィールドが欠落
**対応**：
- `data/roadmap.json`：`task_work_permit` に `"skip_if_profile": {"permit_obtained": true}` を追加
- `models.py`：`permit_obtained` フィールドを追加
- `roadmap_engine.py`：`profile_from_dict` に `permit_obtained` を追加
- `templates/index.html`：「アルバイトする予定？」の下に checkbox を追加（アルバイト選択時のみ表示）
- `static/js/main.js`：`onPartTimePlanChange()` を追加。`submitOnboard`・`getOnboardProfile`・`restoreOnboardFields` に `permit_obtained` の読み書きを追加

### 修正 3：中国語インターフェースに日本語が混入
**根本原因**：`data/roadmap_branches.json` のすべての `zh-TW` フィールドに日本語が入力されていた。

**対応**：`data/roadmap_branches.json` を全面的に翻訳。`branch_points` の `prompt`/`label`/`description` および `supplemental_tasks` の `title`/`summary` をすべて正しい繁体中国語に修正。「ゆうちょ銀行」等の固有名詞のみ日本語を維持。

### 修正 4：学校名・居住地区の入力フィールドが使いにくい
**根本原因**：TomSelect が Enter キー確認後に入力欄を視覚的にクリアし、フォーム送信が発生する場合があった。

**対応**：
- `templates/index.html`：TomSelect の CDN を削除
- `static/js/school_autocomplete.js`：純粋な `<input type="text">` として完全に書き直し。Enter キーで次のフィールドにフォーカス移動

### 修正 5：MOCK モードで無限ポーリング発生
**根本原因**：mock response をクリアした後、`fetchRoadmap` 完了時に再び `fetchAgentDecision` がトリガーされ無限ループが発生。

**対応（`static/js/main.js`）**：
- mock response を `currentDecisionObj` に保存し `lastAgentFingerprint` をセット（クリアしない）
- `fetchAgentDecision` の early-return を `currentDecisionObj` の存在と fingerprint の一致のみで判定
- `fetchRoadmap` 完了後は `!currentDecisionObj` の場合のみ agent-step をトリガー
- GPS コールバックのトリガー条件を `!currentDecisionObj` に統一
- `completed_tasks` はタスク数に変化があった場合のみ roadmap を再取得

### 修正 6：オンボーディング起動時に無応答状態になる
**対応（`static/js/main.js`）**：
- `submitOnboard` 送信前に即座に `showLoading()` を呼びボタンを無効化
- `finally` でロード完了に関わらず `hideLoading()` とボタン復元を保証

### 修正 7：「入国審査・在留カード受領」と「空港で在留カードを受け取ったか？」が重複・矛盾
**根本原因**：同一の手続きに対して 2 つの制御ポイントが存在していた。

**対応**：
- `templates/index.html`：`has_residence_card` のドロップダウンを削除し、「完了済み手続き」ブロックの先頭に checkbox として移動
- `static/js/main.js`：チェック時に `task_immigration` を `completedTasks` に自動追加。動的タスク一覧から `task_immigration` を除外。`restoreOnboardFields` で `setChk` を使用

---

## 三、バックエンド国際化（i18n）リファクタリング

### 新規追加：`backend_i18n.py`
- `data/locales/backend/{lang}.json` から locale pack を読み込み（`_cache` で重複読み込みを防止）
- `t(key, lang, **kwargs)` — 翻訳文字列を取得。`str.format_map()` による変数挿入をサポート。key が見つからない場合は `en` にフォールバック
- `japanese_level_label(code, lang)` — DB に保存された japanese_level コード（旧来の中国語文字列含む）を人間が読める形式に変換

### 新規追加：`data/locales/backend/{en,zh-TW,ja}.json`
agent・PDF・ナビゲーション・ステップ説明・quiz・mock 応答など約 60 個の key を収録。

**主なキー**：
`chipComplete`・`chipMaps`・`chipTask`・`allDone`・`completedNarrative`・`markedCompleteNext`・`navWardOffice`・`navBank`・`navPhone`・`navActionLabel`・`mermaidNextSteps`・`mermaidFull`・`stepReadSummary`・`stepPrepDocs`・`stepMarkComplete`・`greetingBody`・`pdfTitle`・`pdfSectionNow`・`pdfDuration`・`pdfDeadline`・`pdfFooter`・`japaneseLevelBeginner_zero`〜`japaneseLevelAdvanced`

**i18n 完全対応時に追加されたキー**：
`lockReasonPrefix`・`lockReasonSep`・`sectionOverview`・`sectionTips`・`sectionDocuments`・`mockDefaultLocation`・`mockDefaultSchool`・`mockPlanTitle`・`mockStep1`〜`mockStep4`・`quizNoQuestions`・`quizIntro`・`quizDoneHeader`・`quizDoneDefault`・`quizDonePriority`・`wardLinkSuffix`・`officialLinksTitle`・`chipSuggestionsDefault`・`chipSuggestions_task_ward_office`・`chipSuggestions_task_bank`・`chipSuggestions_task_phone`・`guideStartWalkthrough`・`sourceCitationsTitle`・`graphHousingForkLabel`・`graphHousingForkPrompt`・`mockAgentTitle`・`mockAgentNarrative`・`mockAgentActionLabel`・`mockAgentUpcomingHint`・`mockChatReply`・`mockAnalyzeForm`・`mockSttResult`

### `t()` を使用するよう変更したモジュール
- `agent_engine.py` — ナビゲーションクエリ・completed narrative・action label
- `action_plan_builder.py` — ステップフォールバック・PDF 出力文字列・greeting body
- `chat_blocks.py`・`chat_tools.py`・`roadmap_export.py`・`roadmap_mermaid_engine.py` — 各 UI 文字列
- `roadmap_engine.py` — `get_lock_reason()` のプレフィックスと区切り文字
- `roadmap_detail_engine.py` — section タイトル・mock plan の全文字列
- `quiz_engine.py` — quiz フロー全体のインライン dict
- `resource_engine.py` — ward link suffix・official links title・composer chips（locale の `||` 区切り文字列から読み込む形式に変更。新タスク追加は JSON key 追加のみで対応可能）
- `knowledge_engine.py` — guide CTA ラベル・source citations タイトル
- `roadmap_graph_engine.py` — housing fork ノードラベル
- `main.py` — mock モード応答文字列すべて（`from backend_i18n import t as bi18n` を追加）

---

## 四、フロントエンド i18n 追加キー（`static/locales/{en,zh-TW,ja}.json`）

`aiStepsLabel`・`aiGeneratingRoadmap`・`aiRoadmapReady`・`permitObtainedLabel`・`hasResidenceCardLabel`・`onboardingLoading`
