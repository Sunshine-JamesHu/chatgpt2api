"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { ProxyPoolItem } from "@/lib/api";

type ProxyPoolSelectProps = {
  items: ProxyPoolItem[];
  value: string;
  onValueChange: (value: string) => void;
  disabled?: boolean;
};

export function ProxyPoolSelect({ items, value, onValueChange, disabled }: ProxyPoolSelectProps) {
  return (
    <Select value={value || "none"} onValueChange={(next) => onValueChange(next === "none" ? "" : next)} disabled={disabled}>
      <SelectTrigger className="h-11 w-full rounded-xl border-stone-200 bg-white">
        <SelectValue placeholder="选择代理" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="none">无代理</SelectItem>
        {items.map((item) => (
          <SelectItem key={item.id} value={item.id}>{item.name} ({item.url})</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
