# HARU — Cloud Run 部署指南

本文件記錄將 HARU 部署到 Google Cloud Run 的完整流程，包含實際操作時遇到的問題與修正。

## 前置條件

- 有 Google 帳號
- 安裝 [gcloud CLI](https://cloud.google.com/sdk/docs/install)
- 已安裝 Git，且 code 已推上 GitHub repo

---

## Step 1：建立 GCP 專案

1. 開啟 [console.cloud.google.com](https://console.cloud.google.com)
2. 點左上角專案下拉 → **New Project**
3. 輸入專案名稱（例如 `haru-app`）→ **Create**
4. 記下 **Project ID**（不一定等於名稱，長得像 `haru-app-123456`）

---

## Step 2：本機登入 gcloud

```cmd
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

確認登入成功：

```cmd
gcloud projects describe YOUR_PROJECT_ID
```

---

## Step 3：開啟必要的 API

```cmd
gcloud services enable run.googleapis.com ^
  artifactregistry.googleapis.com ^
  firestore.googleapis.com ^
  iam.googleapis.com ^
  iamcredentials.googleapis.com ^
  secretmanager.googleapis.com ^
  cloudbuild.googleapis.com
```

等約 30 秒讓 API 生效。

---

## Step 4：建立 Firestore 資料庫

**必須在 GCP Console UI 操作（CLI 不支援首次建立）：**

1. 直接開啟：`https://console.cloud.google.com/datastore/setup?project=YOUR_PROJECT_ID`
2. 選 **Native mode**（重要，不要選 Datastore mode）
3. Location 選 **asia-northeast1**（東京，與 Cloud Run 同 region）
4. 點 **Create Database**

等待約 1 分鐘建立完成。

> **安全性規則**：Cloud Run 後端使用 Service Account（Admin SDK）存取 Firestore，會繞過安全性規則，保持預設即可。

---

## Step 5：建立 Artifact Registry repository

```cmd
gcloud artifacts repositories create haru ^
  --repository-format=docker ^
  --location=asia-northeast1 ^
  --description="HARU app Docker images"
```

---

## Step 6：把 API 金鑰存進 Secret Manager

建立 secret：

```cmd
gcloud secrets create GEMINI_API_KEY --replication-policy="automatic"
gcloud secrets create GOOGLE_MAPS_API_KEY --replication-policy="automatic"
```

寫入實際的值：

```cmd
echo YOUR_GEMINI_API_KEY | gcloud secrets versions add GEMINI_API_KEY --data-file=-
echo YOUR_MAPS_API_KEY | gcloud secrets versions add GOOGLE_MAPS_API_KEY --data-file=-
```

> Maps key 沒有也沒關係，先存空字串佔位：
> `echo "" | gcloud secrets versions add GOOGLE_MAPS_API_KEY --data-file=-`

---

## Step 7：建立 Service Account（給 GitHub Actions 用）

```cmd
gcloud iam service-accounts create github-actions-haru ^
  --display-name="GitHub Actions HARU"
```

取得完整 email（後面會用到）：

```cmd
gcloud iam service-accounts list
```

格式：`github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com`

---

## Step 8：授予 Service Account 所需權限

把 `YOUR_PROJECT_ID` 換成你的實際 Project ID：

```cmd
rem Cloud Run 部署
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/run.admin"

rem Artifact Registry 推送 image
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/artifactregistry.writer"

rem 讓 Cloud Run service 能以自己的 SA 身份執行
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/iam.serviceAccountUser"

rem 讀取 Secret Manager
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/secretmanager.secretAccessor"
```

---

## Step 9：讓 Cloud Run 本身能存取 Firestore 和 Secrets

取得 project number：

```cmd
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
```

拿到 project number（長得像 `123456789`）後：

```cmd
rem Firestore 讀寫
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" ^
  --role="roles/datastore.user"

rem Secret Manager 讀取
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" ^
  --role="roles/secretmanager.secretAccessor"
```

---

## Step 10：設定 Workload Identity Federation

讓 GitHub Actions 不需要 JSON key 就能操作 GCP。

**取得 project number：**

```cmd
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
```

**建立 WIF pool：**

```cmd
gcloud iam workload-identity-pools create "github-pool" ^
  --location="global" ^
  --display-name="GitHub Actions Pool"
```

**建立 OIDC provider：**

> ⚠️ GCP 現在要求必須加上 `--attribute-condition`，否則會出現：
> `ERROR: INVALID_ARGUMENT: The attribute condition must reference one of the provider's claims.`

```cmd
gcloud iam workload-identity-pools providers create-oidc "github-provider" ^
  --location="global" ^
  --workload-identity-pool="github-pool" ^
  --display-name="GitHub provider" ^
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" ^
  --issuer-uri="https://token.actions.githubusercontent.com" ^
  --attribute-condition="assertion.repository=='YOUR_GITHUB_USERNAME/HARU-main'"
```

**把 GitHub repo 綁定到 SA：**

```cmd
gcloud iam service-accounts add-iam-policy-binding ^
  github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com ^
  --role="roles/iam.workloadIdentityUser" ^
  --member="principalSet://iam.googleapis.com/projects/YOUR_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_GITHUB_USERNAME/HARU-main"
```

**取得 WIF Provider 完整路徑（填入 GitHub Secrets 用）：**

```cmd
gcloud iam workload-identity-pools providers describe github-provider ^
  --location="global" ^
  --workload-identity-pool="github-pool" ^
  --format="value(name)"
```

輸出格式：
`projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider`

---

## Step 11：設定 GitHub Secrets

到 GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

依序新增：

| Name | Value |
|---|---|
| `GCP_PROJECT_ID` | 你的 Project ID（例如 `haru-app-123456`） |
| `WIF_PROVIDER` | Step 10 最後指令輸出的完整路徑 |
| `WIF_SERVICE_ACCOUNT` | `github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com` |

---

## Step 12：第一次部署

確認 `.github/workflows/deploy.yml` 的 `on.push.branches` 為你要用的分支（本專案用 `master`）。

Push 觸發部署：

```cmd
git add .
git commit -m "feat: add Cloud Run deployment"
git push origin master
```

到 GitHub → **Actions** tab 看進度，約 3–5 分鐘。

---

## Step 13：確認部署成功

到 GCP Console → [Cloud Run](https://console.cloud.google.com/run) → 點 **haru** service，頁面最上方有 URL。

或從 GitHub Actions 的 **Deploy to Cloud Run** 步驟找 `Service URL:` 那行。

---

## 遇到的問題與修正記錄

### 問題 1：Container 啟動失敗（port 8080）

**錯誤訊息：**
```
The user-provided container failed to start and listen on the port defined provided by the PORT=8080 environment variable
```

**原因：** `main.py` 有 `from apscheduler.schedulers.asyncio import AsyncIOScheduler` 的 import，但 `requirements.txt` 沒有 `apscheduler` 套件，導致 container 啟動時 import 失敗。

**修正：** 移除未使用的 import。

```python
# 刪除這兩行
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
```

---

### 問題 2：Firestore 連線失敗（project 不存在）

**錯誤訊息：**
```
要求的資源無效：「projects/***」不存在。
```

**原因：** `FirestoreDB.__init__` 在物件建立時就呼叫 `_get_client()`，在 Cloud Run 冷啟動極早期就嘗試連 Firestore，此時環境和憑證尚未就緒。

**修正：** 改為懶初始化，只在第一次實際 DB 操作時才建立 client。

```python
class FirestoreDB:
    def __init__(self):
        self._db: Optional[firestore.AsyncClient] = None  # 不在這裡初始化

    def _client(self) -> firestore.AsyncClient:
        if self._db is None:
            self._db = _get_client()  # 第一次使用時才建立
        return self._db
```

---

### 問題 3：Firestore 資料庫不存在（404）

**錯誤訊息：**
```
404 The database (default) does not exist for project YOUR_PROJECT_ID
```

**原因：** Step 4 的 Firestore 資料庫還沒建立，或建立後尚未生效。

**處理：** 依照 Step 4 建立 Firestore 資料庫（Native mode）。建立完成後不需要重新部署，重新整理頁面即可。

---

### 問題 4：UI 錯誤訊息顯示中文

**原因：** `main.py` 的 `HTTPException detail` 有四個寫死的中文字串，會直接顯示在 app 介面上。

**修正：** 全部改為英文。

```python
# /api/agent/step
"Agent decision failed: {str(e)}"

# /api/export/roadmap-pdf
"Action plan generation failed: {str(e)}"

# /api/chat
"Chat processing failed: {str(e)}"

# /api/analyze-form
"Form analysis failed: {str(e)}"
```

---

## 日後更新 Gemini API Key

**方式 1：更新 Secret Manager（所有用戶共用的伺服器 key）**

1. GCP Console → **Secret Manager** → **GEMINI_API_KEY**
2. 點 **+ New Version** → 貼上新 key → **Add Version**

Cloud Run 不需要重新部署，下次 request 時自動讀到新版本。

**方式 2：在 app 介面設定（per-device 個人 key）**

在 HARU 介面 → **Profile** → **API Key** → 輸入新 key → 儲存。

此 key 優先於 Secret Manager，只影響自己的 device。

---

## 日後重新觸發部署

如果沒有 code 變更但需要重新部署：

**方法 1（推薦）：** GitHub → Actions → 點最近的 run → **Re-run all jobs**

**方法 2：** Push 一個空 commit

```cmd
git commit --allow-empty -m "ci: retrigger deployment"
git push origin master
```

---

## 遷移到其他 GCP 帳號

重新執行 Step 3–10，將新 project 的值填入 GitHub Secrets（`GCP_PROJECT_ID`、`WIF_PROVIDER`、`WIF_SERVICE_ACCOUNT`），push 即可完成遷移。

如需更換 region，修改 `.github/workflows/deploy.yml` 的 `REGION`，並確保 Firestore 和 Artifact Registry 建立在相同 region。

| 地點 | region |
|---|---|
| 東京 | `asia-northeast1` |
| 台灣 | `asia-east1` |
| 新加坡 | `asia-southeast1` |
| 美國東部 | `us-east1` |
