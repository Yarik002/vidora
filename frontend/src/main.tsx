import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { EmptyState } from "./components/ui";
import { AuthProvider } from "./lib/auth";
import { applyTheme, getTheme } from "./lib/theme";
import { Login, Register } from "./pages/Auth";
import { Home } from "./pages/Home";
import { Upload } from "./pages/Upload";
import { Watch } from "./pages/Watch";
import "./styles/tokens.css";
import "./styles/base.css";

applyTheme(getTheme());

function NotFound() {
  return (
    <EmptyState icon="film" title="Страница не найдена">
      <a href="/" className="btn btn--secondary btn--md">
        На главную
      </a>
    </EmptyState>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="watch/:id" element={<Watch />} />
            <Route path="upload" element={<Upload />} />
            <Route path="login" element={<Login />} />
            <Route path="register" element={<Register />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
