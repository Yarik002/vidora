import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { EmptyState } from "./components/ui";
import { AuthProvider } from "./lib/auth";
import { applyTheme, getTheme } from "./lib/theme";
import { Login, Register } from "./pages/Auth";
import { Channel } from "./pages/Channel";
import { History, Liked, MyPlaylists, SearchResults, SubscriptionsFeed, You } from "./pages/Feeds";
import { Home } from "./pages/Home";
import { Moderation } from "./pages/Moderation";
import { PlaylistPage } from "./pages/PlaylistPage";
import { Studio } from "./pages/Studio";
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
            <Route path="results" element={<SearchResults />} />
            <Route path="channel/:handle" element={<Channel />} />
            <Route path="playlist/:id" element={<PlaylistPage />} />
            <Route path="feed/subscriptions" element={<SubscriptionsFeed />} />
            <Route path="feed/history" element={<History />} />
            <Route path="feed/liked" element={<Liked />} />
            <Route path="feed/playlists" element={<MyPlaylists />} />
            <Route path="feed/you" element={<You />} />
            <Route path="studio" element={<Studio />} />
            <Route path="moderation" element={<Moderation />} />
            <Route path="login" element={<Login />} />
            <Route path="register" element={<Register />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
