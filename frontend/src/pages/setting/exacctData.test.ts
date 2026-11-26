/**
 * exacctData 纯函数守卫：ccxt 状态映射、资产分布聚合、CSV 转义、格式化。
 * 不含网络与 mock 账户数据 —— 真实数据契约见 AccountSnapshot。
 */
import { describe, expect, it } from "vitest";
import {
  assetDonut,
  fmtNum,
  fmtSigned,
  mapOrderStatus,
  orderInViewStatus,
  positionPnl,
  toCsv,
} from "./exacctData";
import type { BalanceRow } from "./exacctData";

describe("mapOrderStatus（ccxt 状态 → 页面筛选语义）", () => {
  it("closed → 已成交", () => {
    expect(mapOrderStatus("closed", 12)).toBe("filled");
  });

  it("open 且已有成交量 → 部分成交，否则待成交", () => {
    expect(mapOrderStatus("open", 0.5)).toBe("partial");
    expect(mapOrderStatus("open", 0)).toBe("open");
  });

  it("canceled/expired/rejected → 已撤销", () => {
    for (const s of ["canceled", "expired", "rejected"]) {
      expect(mapOrderStatus(s, 0)).toBe("canceled");
    }
  });

  it("orderInViewStatus 走 filled 字段判定", () => {
    expect(orderInViewStatus({ status: "open", filled: 3 } as never)).toBe("partial");
  });
});

describe("positionPnl", () => {
  it("做多随标记价上涨为正，做空相反；数量取绝对值", () => {
    expect(positionPnl({ qty: 1, entry: 100, mark: 110, side: "long" })).toBeCloseTo(10);
    expect(positionPnl({ qty: 2, entry: 100, mark: 110, side: "short" })).toBeCloseTo(-20);
    expect(positionPnl({ qty: -1, entry: 100, mark: 110, side: "long" })).toBeCloseTo(10);
  });
});

describe("assetDonut（估值聚合）", () => {
  const row = (currency: string, valueUsdt: number): BalanceRow => ({
    currency,
    free: 0,
    used: 0,
    priceUsdt: null,
    valueUsdt,
  });

  it("按价值降序，只计正值", () => {
    const out = assetDonut([row("BTC", 100), row("USDT", 300), row("X", 0)], {
      name: "合约",
      value: 50,
    });
    expect(out.map((r) => r.name)).toEqual(["USDT", "BTC", "合约"]);
  });

  it("超过 topN 合并为 OTHER 且不丢总额", () => {
    const rows = ["A", "B", "C", "D", "E", "F", "G"].map((c, i) => row(c, 100 + i));
    const out = assetDonut(rows, { name: "合约", value: 0 }, 5);
    expect(out).toHaveLength(6);
    const sum = out.reduce((s, r) => s + r.value, 0);
    expect(sum).toBeCloseTo(rows.reduce((s, r) => s + r.valueUsdt, 0));
    expect(out[out.length - 1].name).toBe("OTHER");
  });

  it("同名资产（extra 与余额同币种）合并而非重复", () => {
    const out = assetDonut([row("USDT", 100)], { name: "USDT", value: 200 });
    expect(out).toEqual([{ name: "USDT", value: 300 }]);
  });
});

describe("格式化与 CSV", () => {
  it("fmtNum 千分位 / fmtSigned 补符号", () => {
    expect(fmtNum(1234567.891, 2)).toBe("1,234,567.89");
    expect(fmtSigned(1.5)).toBe("+1.50");
    expect(fmtSigned(-1.5)).toBe("-1.50");
  });

  it("toCsv 带 BOM、CRLF、RFC 4180 转义", () => {
    const csv = toCsv(["a", "b"], [["x,y", 'say "hi"']]);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    expect(csv).toContain("\r\n"); // 行分隔
    expect(csv).toContain('"x,y"');
    expect(csv).toContain('"say ""hi"""');
  });
});
