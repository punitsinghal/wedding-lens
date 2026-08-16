'use client';

import { useState, useEffect } from 'react';

interface Props {
  isOpen: boolean;
  title: string;
  message: string;
  /** If set, the user must type this exact string to confirm */
  confirmText?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  destructive?: boolean;
}

export default function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmText,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
  destructive = false,
}: Props) {
  const [inputValue, setInputValue] = useState('');

  useEffect(() => {
    if (!isOpen) setInputValue('');
  }, [isOpen]);

  if (!isOpen) return null;

  const canConfirm = confirmText ? inputValue === confirmText : true;

  return (
    <div className="dialog-backdrop">
      <div className="dialog">
        <h3 className="dialog-title">{title}</h3>
        <p className="dialog-body">{message}</p>

        {confirmText && (
          <div className="field">
            <label>
              Type <span className="font-semibold">{confirmText}</span> to confirm:
            </label>
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              className="input"
              placeholder={confirmText}
              autoFocus
            />
          </div>
        )}

        <div className="dialog-actions">
          <button onClick={onCancel} className="btn btn-secondary">
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={!canConfirm}
            className={`btn ${destructive ? 'btn-danger-solid' : 'btn-primary'}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
