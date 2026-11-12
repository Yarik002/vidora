import { useState } from "react";
import { api, errorText } from "../lib/api";
import type { ReportReason } from "../lib/types";
import { Button, Modal, TextField } from "./ui";

const REASONS: [ReportReason, string][] = [
  ["sexual", "Материалы сексуального характера"],
  ["violence", "Жестокое или отталкивающее содержание"],
  ["hate", "Дискриминационные высказывания и оскорбления"],
  ["spam", "Спам или ввод в заблуждение"],
  ["misleading", "Дезинформация"],
  ["copyright", "Нарушение авторских прав"],
  ["other", "Другое"],
];

export function ReportDialog({
  target,
  onClose,
}: {
  target: { video_id: string } | { comment_id: string };
  onClose: () => void;
}) {
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [details, setDetails] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!reason) return;
    setState("busy");
    setError(null);
    try {
      await api("/reports", { method: "POST", body: { ...target, reason, details } });
      setState("done");
    } catch (err) {
      setError(errorText(err));
      setState("idle");
    }
  };

  if (state === "done") {
    return (
      <Modal title="Спасибо, жалоба отправлена" onClose={onClose} footer={<Button variant="accent" onClick={onClose}>Закрыть</Button>}>
        <p>Модераторы проверят материал. Если он нарушает правила, его скроют.</p>
      </Modal>
    );
  }

  return (
    <Modal
      title={"video_id" in target ? "Пожаловаться на видео" : "Пожаловаться на комментарий"}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button variant="accent" disabled={!reason || state === "busy"} onClick={submit}>
            Пожаловаться
          </Button>
        </>
      }
    >
      <fieldset className="radio-list">
        <legend className="visually-hidden">Причина</legend>
        {REASONS.map(([value, label]) => (
          <label key={value} className="radio-list__item">
            <input type="radio" name="reason" value={value} checked={reason === value} onChange={() => setReason(value)} />
            {label}
          </label>
        ))}
      </fieldset>
      <TextField
        label="Подробности (необязательно)"
        multiline
        maxLength={1000}
        value={details}
        onChange={(e) => setDetails(e.target.value)}
      />
      {error && <p className="error-text">{error}</p>}
    </Modal>
  );
}
