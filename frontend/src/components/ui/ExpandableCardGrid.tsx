/**
 * 卡片网格 + 行内展开面板（跨全宽、落在被点卡片所在「视觉行」之后）。
 *
 * 背景：卡片与列表只是同一份数据的两种排版，点开必须是同一块详情面板
 * （demo `docs/design/qc-prototype-demo.html` 的 `.md-exp` 口径：同一视觉行 = 相同的
 * `offsetTop`，面板插到该行最后一张卡之后，`grid-column: 1 / -1` 等价于 `Col span=24`）。
 *
 * 为什么测量而不是「数据分块」：卡片用 antd `Row/Col` 的响应式断点（xs 1 / sm 2 / md 3 / lg 4），
 * 每行几张卡取决于容器宽度，分块写死会在中间断点错位。这里在展开时量一次卡片位置，
 * 只把「面板插到哪张卡之后」记为下标，容器尺寸变化时重量。
 *
 * 面板内容由调用方传入（通常就是列表 `expandedRowRender` 里那同一份 JSX），
 * 保证两种形态看到的内容逐字相同。
 */
import { Fragment, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Col, Row, type ColProps } from 'antd';

export interface ExpandableCardGridProps<T> {
  items: T[];
  /** 卡片唯一键（与列表行 key 同一口径，展开态靠它定位） */
  getKey: (item: T) => string | number;
  /** 卡片主体（一般就是 `.qc-card`） */
  renderCard: (item: T) => ReactNode;
  /** 当前展开项的 key；null/undefined = 全部收起 */
  expandedKey?: string | number | null;
  /** 展开面板内容；省略则纯网格（等价于普通 Row/Col） */
  renderExpanded?: (item: T) => ReactNode;
  /** 列断点，默认与其他列表页卡片视图一致 */
  colProps?: ColProps;
  gutter?: [number, number];
  className?: string;
}

const DEFAULT_COL: ColProps = { xs: 24, sm: 12, md: 8, lg: 6 };

export function ExpandableCardGrid<T>({
  items,
  getKey,
  renderCard,
  expandedKey,
  renderExpanded,
  colProps = DEFAULT_COL,
  gutter = [16, 16],
  className,
}: ExpandableCardGridProps<T>) {
  const rowRef = useRef<HTMLDivElement>(null);
  const [panelAfter, setPanelAfter] = useState(-1);

  useLayoutEffect(() => {
    const grid = rowRef.current;
    // 收起态无需计算：panelAfter 只在 expandedKey 非空时参与渲染，下次展开会在绘制前重量
    if (!grid || expandedKey == null || !renderExpanded) return;

    const measure = () => {
      const cards = Array.from(grid.querySelectorAll<HTMLElement>('[data-qc-card]'));
      const activeIndex = cards.findIndex((el) => el.dataset.qcCard === String(expandedKey));
      if (activeIndex < 0) {
        setPanelAfter((prev) => (prev === -1 ? prev : -1));
        return;
      }
      // 1px 容差：断点子元素可能出现亚像素差异，严格等于会把同行卡判成两行
      const rowTop = cards[activeIndex].getBoundingClientRect().top;
      const sameRow = (el: HTMLElement) => Math.abs(el.getBoundingClientRect().top - rowTop) < 1;
      // 只需该视觉行的最后一张卡：从激活卡向后扫到行尾。
      // ponytail: 不做反向扫描——反向循环里覆写 last 会把面板错插到行首之前（上一版的 bug）。
      let last = activeIndex;
      for (let i = activeIndex + 1; i < cards.length && sameRow(cards[i]); i += 1) last = i;
      setPanelAfter((prev) => (prev === last ? prev : last));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(grid);
    window.addEventListener('resize', measure);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [expandedKey, items, renderExpanded]);

  // 面板内容永远取自「被点的那张卡」，而不是被插入位置（视觉行末卡）的数据
  const expandedItem =
    expandedKey != null && renderExpanded
      ? items.find((item) => getKey(item) === expandedKey)
      : undefined;

  return (
    <Row ref={rowRef} gutter={gutter} className={className}>
      {items.map((item, index) => {
        const key = getKey(item);
        return (
          <Fragment key={key}>
            <Col {...colProps} data-qc-card={key}>
              {renderCard(item)}
            </Col>
            {index === panelAfter && expandedItem !== undefined && renderExpanded ? (
              <Col span={24} className="qc-card-exp-slot">
                {renderExpanded(expandedItem)}
              </Col>
            ) : null}
          </Fragment>
        );
      })}
    </Row>
  );
}