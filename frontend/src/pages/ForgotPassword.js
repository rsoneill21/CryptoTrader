/**
 * Forgot Password page.
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { authAPI } from '../services/api';

const ForgotPassword = () => {
  const [requestEmail, setRequestEmail] = useState('');
  const [confirmEmail, setConfirmEmail] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [requestLoading, setRequestLoading] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [requestAlert, setRequestAlert] = useState({ message: '', type: '' });
  const [confirmAlert, setConfirmAlert] = useState({ message: '', type: '' });

  const handleRequestReset = async (e) => {
    e.preventDefault();
    if (!requestEmail) {
      setRequestAlert({ message: 'Please enter your email.', type: 'error' });
      return;
    }

    setRequestLoading(true);
    setRequestAlert({ message: 'Sending reset link...', type: 'neutral' });

    try {
      await authAPI.requestPasswordReset(requestEmail);
      setRequestAlert({
        message: 'If the email exists, you will receive instructions shortly.',
        type: 'success',
      });
      setConfirmEmail(requestEmail);
    } catch (err) {
      setRequestAlert({
        message: err.message || 'Unable to send reset email.',
        type: 'error',
      });
    } finally {
      setRequestLoading(false);
    }
  };

  const handleConfirmReset = async (e) => {
    e.preventDefault();
    if (!confirmEmail || !resetToken || !newPassword || !confirmPassword) {
      setConfirmAlert({ message: 'Complete every field to continue.', type: 'error' });
      return;
    }

    if (newPassword !== confirmPassword) {
      setConfirmAlert({ message: 'Passwords do not match.', type: 'error' });
      return;
    }

    setConfirmLoading(true);
    setConfirmAlert({ message: 'Verifying code...', type: 'neutral' });

    try {
      await authAPI.confirmPasswordReset(resetToken, newPassword);
      setConfirmAlert({
        message: 'Success! You can now log in with your new password.',
        type: 'success',
      });
      setNewPassword('');
      setConfirmPassword('');
      setResetToken('');
    } catch (err) {
      setConfirmAlert({
        message: err.message || 'Unable to reset password.',
        type: 'error',
      });
    } finally {
      setConfirmLoading(false);
    }
  };

  const getAlertClass = (type) => {
    switch (type) {
      case 'success':
        return 'text-emerald-300';
      case 'error':
        return 'text-rose-400';
      default:
        return 'text-slate-400';
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-100 px-4 py-10">
      <div className="w-full max-w-5xl space-y-8 rounded-3xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl shadow-slate-950/60 sm:p-10">
        <header className="space-y-2 text-center">
          <p className="text-xs uppercase tracking-[0.4em] text-cyan-400">Security</p>
          <h1 className="text-3xl font-semibold text-white">Reset your password</h1>
          <p className="text-sm text-slate-400">
            Request a reset link and complete the confirmation.
          </p>
        </header>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Step 1: Request Reset */}
          <section className="space-y-4 rounded-2xl border border-slate-800 bg-slate-950/40 p-6">
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-200">Step 1 · Request reset link</p>
              <p className="text-xs text-slate-400">
                Check your inbox (and spam folder) for the reset code.
              </p>
            </div>
            <form onSubmit={handleRequestReset} className="space-y-4">
              <div>
                <label className="text-xs uppercase tracking-wider text-slate-400">Email</label>
                <input
                  type="email"
                  value={requestEmail}
                  onChange={(e) => setRequestEmail(e.target.value)}
                  className="mt-1 w-full rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-base text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
                  placeholder="you@company.com"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={requestLoading}
                className="w-full rounded-2xl bg-cyan-500 px-4 py-3 text-sm font-semibold uppercase tracking-widest text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {requestLoading ? 'Sending...' : 'Send reset link'}
              </button>
              {requestAlert.message && (
                <p className={`text-sm font-medium ${getAlertClass(requestAlert.type)}`}>
                  {requestAlert.message}
                </p>
              )}
            </form>
          </section>

          {/* Step 2: Confirm Reset */}
          <section className="space-y-4 rounded-2xl border border-slate-800 bg-slate-950/40 p-6">
            <div className="space-y-2">
              <p className="text-sm font-semibold text-slate-200">Step 2 · Confirm reset</p>
              <p className="text-xs text-slate-400">
                Paste the code from the email and pick a new password.
              </p>
            </div>
            <form onSubmit={handleConfirmReset} className="space-y-4">
              <div>
                <label className="text-xs uppercase tracking-wider text-slate-400">Email</label>
                <input
                  type="email"
                  value={confirmEmail}
                  onChange={(e) => setConfirmEmail(e.target.value)}
                  className="mt-1 w-full rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-base text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
                  placeholder="you@company.com"
                  required
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-slate-400">Reset code</label>
                <input
                  type="text"
                  value={resetToken}
                  onChange={(e) => setResetToken(e.target.value)}
                  className="mt-1 w-full rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-base text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
                  placeholder="XXXXXXXX"
                  required
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-slate-400">New password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="mt-1 w-full rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-base text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
                  placeholder="Create a strong password"
                  required
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-slate-400">Confirm password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="mt-1 w-full rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-base text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
                  placeholder="Repeat new password"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={confirmLoading}
                className="w-full rounded-2xl bg-white px-4 py-3 text-sm font-semibold uppercase tracking-widest text-slate-950 transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {confirmLoading ? 'Updating...' : 'Update password'}
              </button>
              {confirmAlert.message && (
                <p className={`text-sm font-medium ${getAlertClass(confirmAlert.type)}`}>
                  {confirmAlert.message}
                </p>
              )}
            </form>
          </section>
        </div>

        <div className="text-center">
          <Link to="/login" className="text-sm text-cyan-400 hover:text-cyan-300 transition">
            Back to Login
          </Link>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;
