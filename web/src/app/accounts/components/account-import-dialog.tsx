"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  ArrowLeft,
  Copy,
  ExternalLink,
  FileText,
  Files,
  KeyRound,
  LoaderCircle,
  LogIn,
  Upload,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { ProxyPoolSelect } from "@/components/proxy-pool-select";
import {
  createAccounts,
  fetchProxyPool,
  finishOAuthLogin,
  startOAuthLogin,
  type Account,
  type AccountImportPayload,
  type OAuthLoginStartResponse,
  type ProxyPoolItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type ImportMethod = "menu" | "token" | "session" | "codex-auth" | "account-json" | "oauth";

type AccountImportDialogProps = {
  disabled?: boolean;
  onImported: (items: Account[]) => void;
};

type PendingAccountJsonImport = {
  tokens: string[];
  accounts: AccountImportPayload[];
  parsedAccountCount: number;
  errorCount: number;
};

const sessionUrl = "https://chatgpt.com/api/auth/session";

function splitTokens(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function getSessionAccessToken(value: unknown) {
  const token = (value as { accessToken?: unknown })?.accessToken;
  return typeof token === "string" ? token.trim() : "";
}

function getAccountJsonAccount(value: unknown): AccountImportPayload | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const tokenValue = raw.access_token ?? raw.accessToken;
  const token = typeof tokenValue === "string" ? tokenValue.trim() : "";
  if (!token) {
    return null;
  }

  const payload: AccountImportPayload = {
    ...raw,
    access_token: token,
    source_type: "codex",
  };
  delete payload.accessToken;
  if (payload.type === "codex") {
    payload.export_type = "codex";
    delete payload.type;
  }
  return payload;
}

function getAccountJsonAccounts(value: unknown): AccountImportPayload[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => getAccountJsonAccount(item))
      .filter((item): item is AccountImportPayload => Boolean(item));
  }

  const singleAccount = getAccountJsonAccount(value);
  if (singleAccount) {
    return [singleAccount];
  }

  if (value && typeof value === "object") {
    const raw = value as Record<string, unknown>;
    const nested = raw.accounts ?? raw.items;
    if (Array.isArray(nested)) {
      return nested
        .map((item) => getAccountJsonAccount(item))
        .filter((item): item is AccountImportPayload => Boolean(item));
    }
  }

  return [];
}

function getCodexAuthAccount(value: unknown): AccountImportPayload | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const tokenValue = raw.access_token ?? raw.accessToken;
  const token = typeof tokenValue === "string" ? tokenValue.trim() : "";
  if (!token) {
    return null;
  }

  const payload: AccountImportPayload = {
    ...raw,
    access_token: token,
    export_type: "codex",
    source_type: "codex",
  };
  delete payload.accessToken;
  if (payload.type === "codex") {
    delete payload.type;
  }
  return payload;
}

function readFileAsText(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(reader.error ?? new Error(`读取文件失败: ${file.name}`));
    reader.readAsText(file);
  });
}

function MethodCard({
  title,
  description,
  icon: Icon,
  onClick,
}: {
  title: string;
  description: string;
  icon: typeof KeyRound;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-2xl border border-stone-200 bg-white p-0 text-left transition hover:border-stone-300 hover:bg-stone-50"
    >
      <Card className="rounded-2xl border-0 bg-transparent shadow-none">
        <CardContent className="flex items-start gap-4 p-4">
          <div className="rounded-xl bg-stone-100 p-3 text-stone-700">
            <Icon className="size-5" />
          </div>
          <div className="space-y-1">
            <div className="text-sm font-semibold text-stone-900">{title}</div>
            <div className="text-sm leading-6 text-stone-500">{description}</div>
          </div>
        </CardContent>
      </Card>
    </button>
  );
}

export function AccountImportDialog({ disabled, onImported }: AccountImportDialogProps) {
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState<ImportMethod>("menu");
  const [tokenInput, setTokenInput] = useState("");
  const [sessionInput, setSessionInput] = useState("");
  const [codexAuthInput, setCodexAuthInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingAccountJsonImport, setPendingAccountJsonImport] = useState<PendingAccountJsonImport | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [oauthSession, setOauthSession] = useState<OAuthLoginStartResponse | null>(null);
  const [oauthCallbackInput, setOauthCallbackInput] = useState("");
  const [oauthStarting, setOauthStarting] = useState(false);
  const [proxyPool, setProxyPool] = useState<ProxyPoolItem[]>([]);
  const [proxyId, setProxyId] = useState("");

  const txtInputRef = useRef<HTMLInputElement | null>(null);
  const accountJsonInputRef = useRef<HTMLInputElement | null>(null);

  const resetState = () => {
    setMethod("menu");
    setTokenInput("");
    setSessionInput("");
    setCodexAuthInput("");
    setPendingAccountJsonImport(null);
    setConfirmOpen(false);
    setOauthSession(null);
    setOauthCallbackInput("");
    setOauthStarting(false);
    setProxyId("");
  };

  useEffect(() => {
    if (!open) return;
    void fetchProxyPool().then((data) => setProxyPool(data.items)).catch(() => toast.error("加载代理列表失败"));
  }, [open]);

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      resetState();
    }
  };

  const submitTokens = async (tokens: string[], successText?: string, accountPayloads: AccountImportPayload[] = []) => {
    const normalizedTokens = tokens.map((item) => item.trim()).filter(Boolean);

    if (normalizedTokens.length === 0) {
      toast.error("请先提供至少一个可用 Token");
      return;
    }

    setIsSubmitting(true);
    try {
      const data = await createAccounts(normalizedTokens, accountPayloads, proxyId);
      onImported(data.items);
      setOpen(false);
      resetState();

      if ((data.errors?.length ?? 0) > 0) {
        const firstError = data.errors?.[0]?.error;
        toast.error(
          `${successText ?? "导入完成"}，新增 ${data.added ?? 0} 个，已刷新 ${data.refreshed ?? 0} 个，失败 ${data.errors?.length ?? 0} 个${firstError ? `，首个错误：${firstError}` : ""}`,
        );
      } else {
        toast.success(
          `${successText ?? "导入完成"}，新增 ${data.added ?? 0} 个，跳过 ${data.skipped ?? 0} 个重复项，已自动刷新账号信息`,
        );
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "导入账户失败";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleImportTokenText = async () => {
    await submitTokens(splitTokens(tokenInput), "Access Token 导入完成");
  };

  const startOAuthSession = async () => {
    setOauthStarting(true);
    try {
      const data = await startOAuthLogin("", proxyId);
      setOauthSession(data);
      setOauthCallbackInput("");
      toast.success("授权链接已生成，请复制后在浏览器中打开，登录后再粘贴 callback URL");
    } catch (error) {
      const message = error instanceof Error ? error.message : "OAuth 起始失败";
      toast.error(message);
    } finally {
      setOauthStarting(false);
    }
  };

  // 起授权：拿 authorize URL，立刻在新窗口打开，方便用户登录
  const handleStartOAuth = async () => {
    await startOAuthSession();
  };

  // 用粘贴回来的 callback URL 完成换 token + 落盘
  const handleFinishOAuth = async () => {
    if (!oauthSession) {
      toast.error("请先点击\"生成授权链接\"获取 session");
      return;
    }
    const trimmed = oauthCallbackInput.trim();
    if (!trimmed) {
      toast.error("请粘贴 callback URL 或 code");
      return;
    }

    setIsSubmitting(true);
    try {
      const data = await finishOAuthLogin(oauthSession.session_id, trimmed);
      onImported(data.items);
      setOpen(false);
      resetState();

      if ((data.errors?.length ?? 0) > 0) {
        const firstError = data.errors?.[0]?.error;
        toast.error(
          `OAuth 登录完成，新增 ${data.added ?? 0} 个，已刷新 ${data.refreshed ?? 0} 个，失败 ${data.errors?.length ?? 0} 个${firstError ? `，首个错误：${firstError}` : ""}`,
        );
      } else {
        toast.success(
          `OAuth 登录完成，新增 ${data.added ?? 0} 个，跳过 ${data.skipped ?? 0} 个重复项，已自动刷新账号信息`,
        );
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "OAuth 换 token 失败";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTxtSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    try {
      const content = await readFileAsText(file);
      const tokens = splitTokens(content);

      if (tokens.length === 0) {
        toast.error("TXT 文件里没有读取到有效 Token");
        return;
      }

      setTokenInput((prev) => {
        const next = [...splitTokens(prev), ...tokens];
        return next.join("\n");
      });
      toast.success(`已从 ${file.name} 读取 ${tokens.length} 个 Token`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "读取 TXT 文件失败";
      toast.error(message);
    }
  };

  const handleImportSessionJson = async () => {
    if (!sessionInput.trim()) {
      toast.error("请先粘贴完整 Session JSON");
      return;
    }

    try {
      const payload = JSON.parse(sessionInput) as unknown;
      const token = getSessionAccessToken(payload);

      if (!token) {
        toast.error("未从 Session JSON 中提取到 accessToken");
        return;
      }

      await submitTokens([token], "Session JSON 导入完成");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Session JSON 解析失败";
      toast.error(message);
    }
  };

  const handleImportCodexAuthJson = async () => {
    if (!codexAuthInput.trim()) {
      toast.error("请先粘贴 Codex 认证 JSON");
      return;
    }

    try {
      const payload = JSON.parse(codexAuthInput) as unknown;
      const account = getCodexAuthAccount(payload);

      if (!account) {
        toast.error("未从 Codex 认证 JSON 中提取到 access_token");
        return;
      }

      await submitTokens([account.access_token], "Codex 认证 JSON 导入完成", [account]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Codex 认证 JSON 解析失败";
      toast.error(message);
    }
  };

  const handleAccountJsonSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";

    if (files.length === 0) {
      return;
    }

    try {
      const results = await Promise.all(
        files.map(async (file) => {
          const raw = await readFileAsText(file);
          const parsed = JSON.parse(raw) as unknown;
          const accounts = getAccountJsonAccounts(parsed);
          return {
            accounts,
          };
        }),
      );

      const accounts = results.flatMap((item) => item.accounts);
      const tokens = accounts.map((item) => item.access_token);
      const parsedAccountCount = accounts.length;
      const errorCount = results.filter((item) => item.accounts.length === 0).length;

      if (parsedAccountCount === 0) {
        toast.error("这些账号 JSON 文件里没有读取到可用 access_token");
        return;
      }

      setPendingAccountJsonImport({
        tokens,
        accounts,
        parsedAccountCount,
        errorCount,
      });
      setConfirmOpen(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : "读取账号 JSON 文件失败";
      toast.error(message);
    }
  };

  const renderMethodBody = () => {
    if (method === "token") {
      const tokenCount = splitTokens(tokenInput).length;

      return (
        <div className="space-y-4">
          <div className="text-xs text-stone-400">当前识别 {tokenCount} 个 Token</div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">Access Token 列表</label>
            <Textarea
              placeholder="每行一个 Access Token..."
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
              className="min-h-56 resize-none rounded-xl border-stone-200"
            />
          </div>
          <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-1">
                <div className="text-sm font-medium text-stone-800">从 TXT 文件导入</div>
                <div className="text-sm leading-6 text-stone-500">支持 `.txt`，文件内容也是一行一个 Token。</div>
              </div>
              <Button
                type="button"
                variant="outline"
                className="rounded-xl border-stone-200 bg-white"
                onClick={() => txtInputRef.current?.click()}
                disabled={isSubmitting}
              >
                <FileText className="size-4" />
                选择 TXT
              </Button>
            </div>
          </div>
          <input
            ref={txtInputRef}
            type="file"
            accept=".txt,text/plain"
            className="hidden"
            onChange={(event) => void handleTxtSelected(event)}
          />
        </div>
      );
    }

    if (method === "session") {
      return (
        <div className="space-y-4">
          <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4 text-sm leading-6 text-stone-600">
            打开
            {" "}
            <a
              href={sessionUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-medium text-stone-900 underline underline-offset-4"
            >
              {sessionUrl}
              <ExternalLink className="size-3.5" />
            </a>
            ，复制页面返回的完整 JSON，系统会自动提取其中的 `accessToken` 导入。
          </div>
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            <div className="font-medium">风险提示</div>
            <div>
              不要使用自己的大号，尽量使用不常用的小号进行导入，避免出现封号风险。本项目不承担任何封号风险责任。
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">Session JSON</label>
            <Textarea
              placeholder='粘贴完整 JSON，例如包含 "accessToken" 的对象...'
              value={sessionInput}
              onChange={(event) => setSessionInput(event.target.value)}
              className="min-h-56 resize-none rounded-xl border-stone-200 font-mono text-xs"
            />
          </div>
        </div>
      );
    }

    if (method === "oauth") {
      return (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              className="h-10 rounded-xl bg-stone-950 text-white hover:bg-stone-800"
              onClick={() => void handleStartOAuth()}
              disabled={oauthStarting}
            >
              {oauthStarting ? <LoaderCircle className="size-4 animate-spin" /> : <ExternalLink className="size-4" />}
              生成授权链接
            </Button>
          </div>
          {oauthSession ? (
            <div className="space-y-3">
              <div className="space-y-2">
                <label className="text-sm font-medium text-stone-700">授权链接</label>
                <div className="flex gap-2">
                  <Textarea readOnly value={oauthSession.authorize_url} className="min-h-20 resize-none rounded-xl border-stone-200 font-mono text-xs" />
                  <Button
                    type="button"
                    variant="outline"
                    className="h-10 shrink-0 rounded-xl border-stone-200 bg-white px-3"
                    onClick={() => void navigator.clipboard.writeText(oauthSession.authorize_url).then(() => toast.success("授权链接已复制"))}
                    title="复制授权链接"
                  >
                    <Copy className="size-4" />
                  </Button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-xl border-stone-200 bg-white"
                  onClick={() => void startOAuthSession()}
                  disabled={oauthStarting}
                >
                  {oauthStarting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                  重新生成授权链接
                </Button>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-stone-700">粘贴 callback URL（或仅 code）</label>
                <Textarea
                  placeholder={"https://platform.openai.com/auth/callback?code=...&state=..."}
                  value={oauthCallbackInput}
                  onChange={(event) => setOauthCallbackInput(event.target.value)}
                  className="min-h-24 resize-none rounded-xl border-stone-200 font-mono text-xs"
                />
              </div>
            </div>
          ) : null}
        </div>
      );
    }

    if (method === "account-json") {
      return (
        <div className="space-y-4">
          <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 p-5">
            <div className="space-y-2">
              <div className="text-sm font-medium text-stone-800">选择本地账号 JSON 文件</div>
              <div className="text-sm leading-6 text-stone-500">
                支持本项目导出的单账号对象或全部账号数组，也兼容每个文件一个账号对象的 CPA JSON。
                系统会自动提取 `access_token` 或 `accessToken`。
              </div>
            </div>
            <Button
              type="button"
              className="mt-4 rounded-xl bg-stone-950 text-white hover:bg-stone-800"
              onClick={() => accountJsonInputRef.current?.click()}
              disabled={isSubmitting}
            >
              <Files className="size-4" />
              选择 JSON 文件
            </Button>
          </div>
          <input
            ref={accountJsonInputRef}
            type="file"
            accept=".json,application/json"
            multiple
            className="hidden"
            onChange={(event) => void handleAccountJsonSelected(event)}
          />
          {pendingAccountJsonImport ? (
            <div className="rounded-2xl border border-stone-200 bg-white p-4 text-sm leading-6 text-stone-600">
              最近一次读取到 {pendingAccountJsonImport.parsedAccountCount} 个 Token
              {pendingAccountJsonImport.errorCount > 0 ? `，另有 ${pendingAccountJsonImport.errorCount} 个文件未提取成功` : ""}。
            </div>
          ) : null}
        </div>
      );
    }

    if (method === "codex-auth") {
      return (
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">Codex 认证 JSON</label>
            <Textarea
              placeholder='粘贴包含 "access_token"、"refresh_token"、"id_token" 的 Codex 认证 JSON...'
              value={codexAuthInput}
              onChange={(event) => setCodexAuthInput(event.target.value)}
              className="min-h-64 resize-none rounded-xl border-stone-200 font-mono text-xs"
            />
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        <MethodCard
          title="OAuth 登录已有账号（带自动刷新）"
          description="用浏览器登录自己的 ChatGPT 账号，回填 callback URL 即可拿到 refresh_token，后台会自动续期。"
          icon={LogIn}
          onClick={() => setMethod("oauth")}
        />
      </div>
    );
  };

  const footerDisabled = disabled || isSubmitting;

  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <Button
          className="h-10 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800"
          onClick={() => setOpen(true)}
          disabled={disabled}
        >
          <Upload className="size-4" />
          导入
        </Button>
        <DialogContent showCloseButton={false} className="flex max-h-[calc(100dvh-2rem)] w-[min(96vw,760px)] flex-col overflow-hidden rounded-2xl p-0">
          <DialogHeader className="shrink-0 gap-2 px-6 pt-6">
            <DialogTitle>
              {method === "menu"
                ? "导入账户"
                : method === "token"
                  ? "导入 Access Token"
                  : method === "session"
                    ? "导入 Session JSON"
                    : method === "codex-auth"
                      ? "导入 Codex 认证 JSON"
                    : method === "oauth"
                      ? "OAuth 登录已有账号"
                      : "导入账号 JSON"}
            </DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {method === "menu"
                ? "选择一种导入方式。导入成功后会自动拉取邮箱、类型和额度。"
                : method === "token"
                  ? "支持手动粘贴或从 TXT 文件导入，一行一个 Token。"
                  : method === "session"
                    ? "粘贴完整 Session JSON，系统会自动提取 accessToken。"
                    : method === "codex-auth"
                      ? "粘贴 Codex 认证 JSON，系统会按 codex 来源导入。"
                    : method === "oauth"
                      ? "用浏览器跑一遍 OpenAI 标准 OAuth，拿回 refresh_token 后系统会自动续期。"
                      : "支持读取本项目导出的单账号对象或全部账号数组，并在提交前做数量确认。"}
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            {method !== "menu" ? (
              <div className="mb-4 space-y-4">
                <button
                  type="button"
                  onClick={() => setMethod("menu")}
                  className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800"
                >
                  <ArrowLeft className="size-4" />
                  返回导入方式
                </button>
                <div className="space-y-2 rounded-xl border border-stone-200 bg-stone-50 p-4">
                  <label className="text-sm font-medium text-stone-700">账号代理</label>
                  <ProxyPoolSelect items={proxyPool} value={proxyId} onValueChange={setProxyId} disabled={isSubmitting || oauthStarting} />
                </div>
              </div>
            ) : null}
            {renderMethodBody()}
          </div>

          <DialogFooter className="shrink-0 border-t border-stone-100 px-6 py-4">
            <Button
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => setOpen(false)}
              disabled={footerDisabled}
            >
              取消
            </Button>
            {method === "token" ? (
              <Button
                className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
                onClick={() => void handleImportTokenText()}
                disabled={footerDisabled}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                导入 Token
              </Button>
            ) : null}
            {method === "session" ? (
              <Button
                className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
                onClick={() => void handleImportSessionJson()}
                disabled={footerDisabled}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                导入 JSON
              </Button>
            ) : null}
            {method === "codex-auth" ? (
              <Button
                className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
                onClick={() => void handleImportCodexAuthJson()}
                disabled={footerDisabled}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                导入 JSON
              </Button>
            ) : null}
            {method === "oauth" ? (
              <Button
                className={cn(
                  "h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800",
                  !oauthSession ? "hidden" : "",
                )}
                onClick={() => void handleFinishOAuth()}
                disabled={footerDisabled || !oauthSession || !oauthCallbackInput.trim()}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                完成导入
              </Button>
            ) : null}
            {method === "account-json" ? (
              <Button
                className={cn(
                  "h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800",
                  !pendingAccountJsonImport ? "hidden" : "",
                )}
                onClick={() => setConfirmOpen(true)}
                disabled={footerDisabled || !pendingAccountJsonImport}
              >
                查看导入确认
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>确认导入账号 Token</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {pendingAccountJsonImport
                ? `确认识别到 ${pendingAccountJsonImport.parsedAccountCount} 个 Token，是否确认导入？`
                : "尚未读取到可导入的 Token。"}
              {pendingAccountJsonImport?.errorCount
                ? `，另有 ${pendingAccountJsonImport.errorCount} 个文件未提取成功。`
                : "。"}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="pt-2">
            <Button
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => setConfirmOpen(false)}
              disabled={isSubmitting}
            >
              返回
            </Button>
            <Button
              className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
              onClick={() =>
                void submitTokens(
                  pendingAccountJsonImport?.tokens ?? [],
                  "账号 JSON 导入完成",
                  pendingAccountJsonImport?.accounts ?? [],
                )
              }
              disabled={isSubmitting || !pendingAccountJsonImport}
            >
              {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
              确认导入
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
