"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="mx-auto max-w-7xl px-6 py-12">
          <div className="rounded border border-danger/30 bg-danger/5 p-6">
            <h2 className="text-lg font-semibold text-danger">Paper Trading ekranı yüklenemedi</h2>
            <p className="mt-2 text-sm text-muted">
              {this.state.error?.message || "Beklenmeyen bir hata oluştu."}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="mt-4 rounded bg-primary px-4 py-2 text-sm text-white"
            >
              Yeniden Dene
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
