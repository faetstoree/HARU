# HARU — Cloud Run デプロイガイド

このドキュメントは HARU を Google Cloud Run にデプロイする完全な手順を記録したものです。デプロイ時に発生した問題とその修正内容も含みます。

## 前提条件

- Google アカウント
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) のインストール
- Git のインストール、および GitHub リポジトリへのコードのプッシュ

---

## Step 1：GCP プロジェクトの作成

1. [console.cloud.google.com](https://console.cloud.google.com) を開く
2. 左上のプロジェクトドロップダウンをクリック → **新しいプロジェクト**
3. プロジェクト名を入力（例：`haru-app`）→ **作成**
4. **プロジェクト ID** をメモしておく（名前と異なる場合があり、`haru-app-123456` のような形式）

---

## Step 2：ローカルで gcloud にログイン

```cmd
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

ログインを確認：

```cmd
gcloud projects describe YOUR_PROJECT_ID
```

---

## Step 3：必要な API を有効にする

```cmd
gcloud services enable run.googleapis.com ^
  artifactregistry.googleapis.com ^
  firestore.googleapis.com ^
  iam.googleapis.com ^
  iamcredentials.googleapis.com ^
  secretmanager.googleapis.com ^
  cloudbuild.googleapis.com
```

API が有効になるまで約 30 秒待ちます。

---

## Step 4：Firestore データベースの作成

**GCP Console の UI から操作する必要があります（CLI では初回作成不可）：**

1. 直接開く：`https://console.cloud.google.com/datastore/setup?project=YOUR_PROJECT_ID`
2. **ネイティブモード** を選択（重要：Datastore モードは選ばない）
3. ロケーションは **asia-northeast1**（東京、Cloud Run と同じリージョン）を選択
4. **データベースを作成** をクリック

作成完了まで約 1 分待ちます。

> **セキュリティルール：** Cloud Run バックエンドは Service Account（Admin SDK）を使って Firestore にアクセスするため、セキュリティルールをバイパスします。デフォルト設定のままで問題ありません。

---

## Step 5：Artifact Registry リポジトリの作成

```cmd
gcloud artifacts repositories create haru ^
  --repository-format=docker ^
  --location=asia-northeast1 ^
  --description="HARU app Docker images"
```

---

## Step 6：Secret Manager に API キーを保存

シークレットを作成：

```cmd
gcloud secrets create GEMINI_API_KEY --replication-policy="automatic"
gcloud secrets create GOOGLE_MAPS_API_KEY --replication-policy="automatic"
```

実際の値を書き込む：

```cmd
echo YOUR_GEMINI_API_KEY | gcloud secrets versions add GEMINI_API_KEY --data-file=-
echo YOUR_MAPS_API_KEY | gcloud secrets versions add GOOGLE_MAPS_API_KEY --data-file=-
```

> Maps キーがない場合は空文字列でプレースホルダーとして保存：
> `echo "" | gcloud secrets versions add GOOGLE_MAPS_API_KEY --data-file=-`

---

## Step 7：Service Account の作成（GitHub Actions 用）

```cmd
gcloud iam service-accounts create github-actions-haru ^
  --display-name="GitHub Actions HARU"
```

完全なメールアドレスを確認（後で使用）：

```cmd
gcloud iam service-accounts list
```

形式：`github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com`

---

## Step 8：Service Account に権限を付与

`YOUR_PROJECT_ID` を実際のプロジェクト ID に置き換えてください：

```cmd
rem Cloud Run デプロイ
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/run.admin"

rem Artifact Registry へのイメージプッシュ
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/artifactregistry.writer"

rem Cloud Run が自身の SA として実行できるようにする
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/iam.serviceAccountUser"

rem Secret Manager の読み取り
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com" ^
  --role="roles/secretmanager.secretAccessor"
```

---

## Step 9：Cloud Run 自身が Firestore と Secrets にアクセスできるようにする

プロジェクト番号を取得：

```cmd
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
```

プロジェクト番号（例：`123456789`）を使って：

```cmd
rem Firestore 読み書き
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" ^
  --role="roles/datastore.user"

rem Secret Manager 読み取り
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID ^
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" ^
  --role="roles/secretmanager.secretAccessor"
```

---

## Step 10：Workload Identity Federation の設定

GitHub Actions が JSON キーなしで GCP を操作できるようにします。

**プロジェクト番号を取得：**

```cmd
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
```

**WIF プールを作成：**

```cmd
gcloud iam workload-identity-pools create "github-pool" ^
  --location="global" ^
  --display-name="GitHub Actions Pool"
```

**OIDC プロバイダーを作成：**

> ⚠️ GCP は現在 `--attribute-condition` の指定を必須としています。指定しない場合：
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

**GitHub リポジトリを SA にバインド：**

```cmd
gcloud iam service-accounts add-iam-policy-binding ^
  github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com ^
  --role="roles/iam.workloadIdentityUser" ^
  --member="principalSet://iam.googleapis.com/projects/YOUR_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_GITHUB_USERNAME/HARU-main"
```

**WIF プロバイダーの完全パスを取得（GitHub Secrets に入力するため）：**

```cmd
gcloud iam workload-identity-pools providers describe github-provider ^
  --location="global" ^
  --workload-identity-pool="github-pool" ^
  --format="value(name)"
```

出力形式：
`projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider`

---

## Step 11：GitHub Secrets の設定

GitHub リポジトリ → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

以下の 3 つを追加：

| Name | Value |
|---|---|
| `GCP_PROJECT_ID` | プロジェクト ID（例：`haru-app-123456`） |
| `WIF_PROVIDER` | Step 10 最後のコマンドで出力された完全パス |
| `WIF_SERVICE_ACCOUNT` | `github-actions-haru@YOUR_PROJECT_ID.iam.gserviceaccount.com` |

---

## Step 12：初回デプロイ

`.github/workflows/deploy.yml` の `on.push.branches` が使用するブランチになっていることを確認（このプロジェクトでは `master`）。

プッシュしてデプロイを起動：

```cmd
git add .
git commit -m "feat: add Cloud Run deployment"
git push origin master
```

GitHub → **Actions** タブで進捗を確認します。約 3〜5 分かかります。

---

## Step 13：デプロイ確認

GCP Console → [Cloud Run](https://console.cloud.google.com/run) → **haru** サービスをクリック。ページ上部に URL が表示されます。

または GitHub Actions の **Deploy to Cloud Run** ステップで `Service URL:` の行を確認します。

---

## Gemini API キーの更新

**方法 1：Secret Manager を更新（全ユーザー共有のサーバーキー）**

1. GCP Console → **Secret Manager** → **GEMINI_API_KEY**
2. **+ 新しいバージョン** をクリック → 新しいキーを貼り付け → **バージョンを追加**

Cloud Run は次のリクエスト時に自動的に新しいバージョンを読み込みます。再デプロイは不要です。

**方法 2：アプリの UI で設定（デバイスごとの個人キー）**

HARU インターフェース → **Profile** → **API Key** → 新しいキーを入力 → 保存。

このキーは Secret Manager のキーより優先され、自分のデバイスのみに影響します。

---

## デプロイの再実行

コード変更なしに再デプロイが必要な場合：

**方法 1（推奨）：** GitHub → Actions → 最新の run をクリック → **Re-run all jobs**

**方法 2：** 空のコミットをプッシュ

```cmd
git commit --allow-empty -m "ci: retrigger deployment"
git push origin master
```

---

## 別の GCP アカウントへの移行

新しいプロジェクトで Step 3〜10 を再実行し、GitHub Secrets（`GCP_PROJECT_ID`、`WIF_PROVIDER`、`WIF_SERVICE_ACCOUNT`）を新しいプロジェクトの値に更新してプッシュするだけで移行完了です。

リージョンを変更する場合は `.github/workflows/deploy.yml` の `REGION` を更新し、Firestore と Artifact Registry も同じリージョンに作成してください。

| 場所 | リージョン |
|---|---|
| 東京 | `asia-northeast1` |
| 台湾 | `asia-east1` |
| シンガポール | `asia-southeast1` |
| 米国東部 | `us-east1` |
