import { createElement, forwardRef } from "react";
import type { IconNode, IconProps } from "@tabler/icons-react";

const defaultAttrs = {
  outline: {
    xmlns: "http://www.w3.org/2000/svg",
    width: 24,
    height: 24,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  },
  filled: {
    xmlns: "http://www.w3.org/2000/svg",
    width: 24,
    height: 24,
    viewBox: "0 0 24 24",
    fill: "currentColor",
    stroke: "none",
  },
};

const createIconComponent = (type: "outline" | "filled", iconName: string, iconAttrs: Record<string, string | number>, iconNode: IconNode) => {
  const Component = forwardRef<SVGSVGElement, IconProps>(({ color = "currentColor", size = 24, stroke = 2, title, className, children, ...rest }: IconProps, ref) =>
    createElement(
      "svg",
      {
        ref,
        ...defaultAttrs[type],
        ...iconAttrs,
        width: size,
        height: size,
        className: ["icon", className].filter(Boolean).join(" "),
        ...(type === "filled"
          ? {
              fill: color,
            }
          : {
              strokeWidth: stroke,
              stroke: color,
            }),
        ...rest,
      },
      [
        title && createElement("title", { key: "svg-title" }, title),
        // tabler 的 IconNode 中 tag 为 SVG 标签名，React 19 的 createElement
        // 对 type 参数类型收紧，这里断言为 string 以通过类型检查
        ...iconNode.map(([tag, attrs]) => createElement(tag as string, attrs)),
        ...(Array.isArray(children) ? children : [children]),
      ]
    )
  );

  Component.displayName = iconName;

  return Component;
};

export default createIconComponent;
