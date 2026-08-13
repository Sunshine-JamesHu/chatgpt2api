"use client";

import { useEffect, useState } from "react";
import { LoaderCircle, Pencil, Plus, Trash2, Wifi } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { createProxyPoolItem, deleteProxyPoolItem, fetchProxyPool, testProxyPoolItem, updateProxyPoolItem, type ProxyPoolItem } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";

const emptyForm = { name: "", url: "" };

export default function ProxiesPage() {
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);
  const [items, setItems] = useState<ProxyPoolItem[]>([]);
  const [editing, setEditing] = useState<ProxyPoolItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const load = async () => { try { setItems((await fetchProxyPool()).items); } catch (error) { toast.error(error instanceof Error ? error.message : "加载代理失败"); } };
  useEffect(() => { if (session?.role === "admin") void load(); }, [session?.role]);
  const close = () => { setCreating(false); setEditing(null); setForm(emptyForm); };
  const save = async () => { setSaving(true); try { const data = editing ? await updateProxyPoolItem(editing.id, form) : await createProxyPoolItem(form); setItems(data.items); close(); toast.success("代理已保存"); } catch (error) { toast.error(error instanceof Error ? error.message : "保存代理失败"); } finally { setSaving(false); } };
  if (isCheckingAuth || !session || session.role !== "admin") return <div className="flex min-h-[40vh] items-center justify-center"><LoaderCircle className="size-5 animate-spin text-stone-400" /></div>;
  return <div className="space-y-5"><div className="flex flex-wrap items-end justify-between gap-3"><div><h1 className="text-2xl font-semibold text-stone-950">代理管理</h1><p className="mt-1 text-sm text-stone-500">保存并维护账号专属代理。</p></div><Button className="h-10 rounded-xl bg-stone-950 text-white hover:bg-stone-800" onClick={() => setCreating(true)}><Plus className="size-4" />添加代理</Button></div><div className="overflow-x-auto rounded-xl border border-stone-200 bg-white"><Table><TableHeader><TableRow><TableHead>名称</TableHead><TableHead>代理地址</TableHead><TableHead className="w-40">操作</TableHead></TableRow></TableHeader><TableBody>{items.map((item) => <TableRow key={item.id}><TableCell className="font-medium text-stone-900">{item.name}</TableCell><TableCell><code className="text-xs text-stone-600">{item.url}</code></TableCell><TableCell><div className="flex gap-1"><Button variant="ghost" size="icon" title="测试代理" disabled={testing === item.id} onClick={() => void (async () => { setTesting(item.id); try { const r = await testProxyPoolItem(item.id); r.result.ok ? toast.success(`代理可用（${r.result.latency_ms} ms）`) : toast.error(r.result.error ?? "代理不可用"); } catch (e) { toast.error(e instanceof Error ? e.message : "测试失败"); } finally { setTesting(null); } })()}><Wifi className="size-4" /></Button><Button variant="ghost" size="icon" title="编辑代理" onClick={() => { setEditing(item); setForm({ name: item.name, url: item.url }); }}><Pencil className="size-4" /></Button><Button variant="ghost" size="icon" title="删除代理" onClick={() => void (async () => { try { setItems((await deleteProxyPoolItem(item.id)).items); toast.success("代理已删除"); } catch (e) { toast.error(e instanceof Error ? e.message : "删除失败"); } })()}><Trash2 className="size-4 text-rose-600" /></Button></div></TableCell></TableRow>)}{items.length === 0 ? <TableRow><TableCell colSpan={3} className="py-12 text-center text-stone-500">暂无代理</TableCell></TableRow> : null}</TableBody></Table></div><Dialog open={creating || Boolean(editing)} onOpenChange={(open) => { if (!open) close(); }}><DialogContent className="rounded-xl"><DialogHeader><DialogTitle>{editing ? "编辑代理" : "添加代理"}</DialogTitle><DialogDescription>支持 HTTP(S) 和 SOCKS 代理地址。</DialogDescription></DialogHeader><div className="space-y-4"><div className="space-y-2"><label className="text-sm font-medium">名称</label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="日本东京线路" /></div><div className="space-y-2"><label className="text-sm font-medium">代理地址</label><Input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="socks5h://user:pass@127.0.0.1:7890" /></div></div><DialogFooter><Button variant="secondary" onClick={close} disabled={saving}>取消</Button><Button onClick={() => void save()} disabled={saving}>{saving ? <LoaderCircle className="size-4 animate-spin" /> : null}保存</Button></DialogFooter></DialogContent></Dialog></div>;
}
