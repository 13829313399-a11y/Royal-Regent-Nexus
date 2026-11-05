// @vitest-environment jsdom
/**
 * ErrorBoundary：子树 render 崩溃时显示错误内容而不是白屏（2026-10-19 文员白屏反馈的兜底）。
 * 运行：npx vitest run scripts/error-boundary.test.jsx
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ErrorBoundary from '../src/components/ErrorBoundary';

function Boom() {
  throw new TypeError("Cannot read properties of undefined (reading 'map')");
}

describe('ErrorBoundary', () => {
  it('正常子树原样渲染', () => {
    render(<ErrorBoundary><div>一切正常</div></ErrorBoundary>);
    expect(screen.getByText('一切正常')).toBeTruthy();
  });

  it('子树 render 抛错 → 显示错误信息而非空白', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {}); // 压住 React 的错误日志
    const { container } = render(<ErrorBoundary><Boom /></ErrorBoundary>);
    spy.mockRestore();
    expect(container.textContent).toContain('页面出错了');
    expect(container.textContent).toContain("reading 'map'");
    expect(screen.getByText('刷新重试')).toBeTruthy();
  });
});
