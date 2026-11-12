// Mirrors backend/app/schemas. Keep in sync with /openapi.json.

export type Role = "user" | "moderator" | "admin";
export type Visibility = "public" | "unlisted" | "private";
export type VideoStatus = "uploading" | "uploaded" | "processing" | "ready" | "failed";

export interface ChannelBrief {
  id: string;
  handle: string;
  title: string;
  avatar_color: string;
  subscribers_count: number;
}

export interface Me {
  id: string;
  email: string;
  username: string;
  role: Role;
  created_at: string;
  channel: ChannelBrief;
}

export interface Page<T> {
  items: T[];
  has_more: boolean;
  offset: number;
  limit: number;
}

export interface VideoCard {
  id: string;
  title: string;
  duration_seconds: number | null;
  views_count: number;
  published_at: string | null;
  created_at: string;
  visibility: Visibility;
  status: VideoStatus;
  thumbnail_url: string | null;
  channel: ChannelBrief;
}

export interface VideoDetail extends VideoCard {
  description: string;
  likes_count: number;
  dislikes_count: number;
  comments_count: number;
  moderation_state: "active" | "hidden";
  processing_error: string | null;
  tags: string[];
  qualities: string[];
  my_reaction: number;
  is_subscribed: boolean;
  is_owner: boolean;
}

export interface VideoStatusOut {
  id: string;
  status: VideoStatus;
  processing_error: string | null;
  duration_seconds: number | null;
  thumbnail_url: string | null;
}

export interface UploadOut {
  upload_id: string;
  video_id: string;
  part_size: number;
  parts: { part_number: number; url: string }[];
  expires_at: string;
}

export interface CommentAuthor {
  id: string;
  username: string;
  channel_handle: string;
  channel_title: string;
  avatar_color: string;
}

export interface Comment {
  id: string;
  video_id: string;
  parent_id: string | null;
  body: string | null;
  author: CommentAuthor | null;
  likes_count: number;
  replies_count: number;
  created_at: string;
  edited: boolean;
  is_deleted: boolean;
  is_video_owner: boolean;
  my_reaction: number;
  can_edit: boolean;
  can_delete: boolean;
}

export interface AccessGrant {
  user_id: string;
  username: string;
  created_at: string;
}

export interface ChannelDetail extends ChannelBrief {
  description: string;
  created_at: string;
  videos_count: number;
  is_subscribed: boolean;
  is_owner: boolean;
}

export interface Playlist {
  id: string;
  title: string;
  description: string;
  visibility: Visibility;
  items_count: number;
  thumbnail_url: string | null;
  channel: ChannelBrief;
  updated_at: string;
  contains_video?: boolean | null;
}

export interface PlaylistDetail extends Playlist {
  videos: VideoCard[];
  is_owner: boolean;
}

export type ReportReason = "spam" | "violence" | "hate" | "sexual" | "copyright" | "misleading" | "other";

export interface Report {
  id: string;
  reason: ReportReason;
  details: string;
  status: "open" | "resolved" | "dismissed";
  created_at: string;
  reporter: string | null;
  video: VideoCard | null;
  video_moderation_state: "active" | "hidden" | null;
  comment: { id: string; body: string | null; author: string | null; video_id: string } | null;
  reports_on_target: number;
}

export interface ModerationAction {
  id: string;
  action: string;
  moderator: string | null;
  reason: string;
  created_at: string;
  video_id: string | null;
  video_title: string | null;
  comment_id: string | null;
  target_user: string | null;
}

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  videos_count: number;
}
