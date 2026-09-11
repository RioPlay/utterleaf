/*
 * Copyright (C) 2013 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// Utterleaf modification: reject suggestion work and results from expired editor sessions.
package com.android.inputmethod.latin.inputlogic;

import android.os.Handler;
import android.os.HandlerThread;
import android.os.Message;
import android.os.Looper;

import org.utterleaf.keyboard.SuggestionDecoder;

import com.android.inputmethod.compat.LooperCompatUtils;
import com.android.inputmethod.latin.LatinIME;
import com.android.inputmethod.latin.SuggestedWords;
import com.android.inputmethod.latin.Suggest.OnGetSuggestedWordsCallback;
import com.android.inputmethod.latin.common.InputPointers;

/**
 * A helper to manage deferred tasks for the input logic.
 */
class InputLogicHandler implements Handler.Callback {
    final Handler mNonUIThreadHandler;
    // TODO: remove this reference.
    final LatinIME mLatinIME;
    final InputLogic mInputLogic;
    private final Object mLock = new Object();
    private final Handler mOwnerHandler = new Handler(Looper.getMainLooper());
    // Tail callbacks publish under the session gate; volatile avoids taking mLock in reverse order.
    private volatile boolean mInBatchInput;
    private volatile boolean mDestroyed;

    private static final int MSG_GET_SUGGESTED_WORDS = 1;

    private static final class SuggestionRequest {
        final Object session;
        final OnGetSuggestedWordsCallback callback;
        final SuggestionDecoder decoder;

        SuggestionRequest(final Object session, final SuggestionDecoder decoder,
                final OnGetSuggestedWordsCallback callback) {
            this.session = session;
            this.decoder = decoder;
            this.callback = callback;
        }
    }

    // A handler that never does anything. This is used for cases where events come before anything
    // is initialized, though probably only the monkey can actually do this.
    public static final InputLogicHandler NULL_HANDLER = new InputLogicHandler() {
        @Override
        public void reset() {}
        @Override
        public boolean handleMessage(final Message msg) { return true; }
        @Override
        public void onStartBatchInput() {}
        @Override
        public void onUpdateBatchInput(final InputPointers batchPointers,
                final int sequenceNumber) {}
        @Override
        public void onCancelBatchInput() {}
        @Override
        public void updateTailBatchInput(final InputPointers batchPointers,
                final int sequenceNumber) {}
        @Override
        public void getSuggestedWords(final int sessionId, final int sequenceNumber,
                final OnGetSuggestedWordsCallback callback) {}
    };

    InputLogicHandler() {
        mNonUIThreadHandler = null;
        mLatinIME = null;
        mInputLogic = null;
    }

    public InputLogicHandler(final LatinIME latinIME, final InputLogic inputLogic) {
        final HandlerThread handlerThread = new HandlerThread(
                InputLogicHandler.class.getSimpleName());
        handlerThread.start();
        mNonUIThreadHandler = new Handler(handlerThread.getLooper(), this);
        mLatinIME = latinIME;
        mInputLogic = inputLogic;
    }

    public void reset() {
        synchronized (mLock) {
            mOwnerHandler.removeCallbacksAndMessages(null);
            if (mNonUIThreadHandler != null) mNonUIThreadHandler.removeCallbacksAndMessages(null);
            mInBatchInput = false;
        }
    }

    // In unit tests, we create several instances of LatinIME, which results in several instances
    // of InputLogicHandler. To avoid these handlers lingering, we call this.
    public void destroy() {
        synchronized (mLock) {
            mDestroyed = true;
            reset();
        }
        // Already-running decoding finishes independently; never block the owner on JNI.
        if (mNonUIThreadHandler != null) {
            LooperCompatUtils.quitSafely(mNonUIThreadHandler.getLooper());
        }
    }

    /**
     * Handle a message.
     * @see android.os.Handler.Callback#handleMessage(android.os.Message)
     */
    // Called on the Non-UI handler thread by the Handler code.
    @Override
    public boolean handleMessage(final Message msg) {
        switch (msg.what) {
            case MSG_GET_SUGGESTED_WORDS:
                final SuggestionRequest request = (SuggestionRequest) msg.obj;
                if (mDestroyed || !mLatinIME.mEditorSession.isCurrent(request.session)) break;
                // Decoding stays outside the gate: lifecycle transitions must never await it.
                request.decoder.decode(suggestedWords ->
                                mLatinIME.mEditorSession.publish(request.session,
                                        () -> {
                                            if (!mDestroyed) request.callback.onGetSuggestedWords(suggestedWords);
                                        }));
                break;
        }
        return true;
    }

    // Called on the UI thread by InputLogic.
    public void onStartBatchInput() {
        synchronized (mLock) {
            if (mDestroyed) return;
            mInBatchInput = true;
        }
    }

    public boolean isInBatchInput() {
        return mInBatchInput;
    }

    /**
     * Fetch suggestions corresponding to an update of a batch input.
     * @param batchPointers the updated pointers, including the part that was passed last time.
     * @param sequenceNumber the sequence number associated with this batch input.
     * @param isTailBatchInput true if this is the end of a batch input, false if it's an update.
     */
    // This method can be called from any thread and will see to it that the correct threads
    // are used for parts that require it. This method will send a message to the Non-UI handler
    // thread to pull suggestions, and get the inlined callback to get called on the Non-UI
    // handler thread. If this is the end of a batch input, the callback will then proceed to
    // send a message to the UI handler in LatinIME so that showing suggestions can be done on
    // the UI thread.
    private void updateBatchInput(final InputPointers batchPointers,
            final int sequenceNumber, final boolean isTailBatchInput) {
        synchronized (mLock) {
            if (mDestroyed || !mInBatchInput) return;
            if (Looper.myLooper() != Looper.getMainLooper()) {
                // External/timer callers may supply mutable arrays. Copy them before returning,
                // then capture all editor state on its owner, rejecting intervening cancellation.
                final Object session = mLatinIME.mEditorSession.capture();
                final InputPointers copiedPointers = new InputPointers(batchPointers.getPointerSize());
                copiedPointers.copy(batchPointers);
                mOwnerHandler.post(() -> {
                    synchronized (mLock) {
                        if (!mLatinIME.mEditorSession.isCurrent(session)) return;
                        updateBatchInput(copiedPointers, sequenceNumber, isTailBatchInput);
                    }
                });
                return;
            }
            if (!mInBatchInput) {
                // Batch input has ended or canceled while the message was being delivered.
                return;
            }
            mInputLogic.mWordComposer.setBatchInputPointers(batchPointers);
            final SuggestedWords previousSuggestions = mInputLogic.mSuggestedWords;
            final OnGetSuggestedWordsCallback callback = new OnGetSuggestedWordsCallback() {
                @Override
                public void onGetSuggestedWords(final SuggestedWords suggestedWords) {
                    showGestureSuggestionsWithPreviewVisuals(suggestedWords, previousSuggestions,
                            isTailBatchInput);
                }
            };
            getSuggestedWords(isTailBatchInput ? SuggestedWords.INPUT_STYLE_TAIL_BATCH
                    : SuggestedWords.INPUT_STYLE_UPDATE_BATCH, sequenceNumber, callback);
        }
    }

    void showGestureSuggestionsWithPreviewVisuals(final SuggestedWords suggestedWordsForBatchInput,
            final SuggestedWords previousSuggestions, final boolean isTailBatchInput) {
        final SuggestedWords suggestedWordsToShowSuggestions;
        // We're now inside the callback. This always runs on the Non-UI thread,
        // no matter what thread updateBatchInput was originally called on.
        if (suggestedWordsForBatchInput.isEmpty()) {
            // Use the fallback captured with this request, never live editor state.
            suggestedWordsToShowSuggestions = previousSuggestions;
        } else {
            suggestedWordsToShowSuggestions = suggestedWordsForBatchInput;
        }
        mLatinIME.mHandler.showGesturePreviewAndSuggestionStrip(suggestedWordsToShowSuggestions,
                isTailBatchInput /* dismissGestureFloatingPreviewText */);
        if (isTailBatchInput) {
            mInBatchInput = false;
            // The following call schedules onEndBatchInputInternal
            // to be called on the UI thread.
            mLatinIME.mHandler.showTailBatchInputResult(suggestedWordsToShowSuggestions);
        }
    }

    /**
     * Update a batch input.
     *
     * This fetches suggestions and updates the suggestion strip and the floating text preview.
     *
     * @param batchPointers the updated batch pointers.
     * @param sequenceNumber the sequence number associated with this batch input.
     */
    // Called on the UI thread by InputLogic.
    public void onUpdateBatchInput(final InputPointers batchPointers,
            final int sequenceNumber) {
        updateBatchInput(batchPointers, sequenceNumber, false /* isTailBatchInput */);
    }

    /**
     * Cancel a batch input.
     *
     * Note that as opposed to updateTailBatchInput, we do the UI side of this immediately on the
     * same thread, rather than get this to call a method in LatinIME. This is because
     * canceling a batch input does not necessitate the long operation of pulling suggestions.
     */
    // Called on the UI thread by InputLogic.
    public void onCancelBatchInput() {
        invalidatePendingRequests();
    }

    /** Retire both queued and running requests without reopening a finished editor. */
    public void invalidatePendingRequests() {
        synchronized (mLock) {
            if (mDestroyed) return;
            // Keep the same lock order as updateBatchInput -> getSuggestedWords. Renewal
            // outside mLock would let a concurrent old update adopt the new request identity.
            if (mLatinIME != null) mLatinIME.mEditorSession.renewIfActive();
            // Reentrant reset drops queued immutable snapshots as well as batch state.
            reset();
            // Before new-current requests can enter, detach results already queued by an
            // old completion. Never take mLock from a completion's session publication gate.
            if (mLatinIME != null) mLatinIME.mHandler.cancelPendingSuggestionResults();
        }
    }

    /**
     * Trigger an update for a tail batch input.
     *
     * A tail batch input is the last update for a gesture, the one that is triggered after the
     * user lifts their finger. This method schedules fetching suggestions on the non-UI thread,
     * then when the suggestions are computed it comes back on the UI thread to update the
     * suggestion strip, commit the first suggestion, and dismiss the floating text preview.
     *
     * @param batchPointers the updated batch pointers.
     * @param sequenceNumber the sequence number associated with this batch input.
     */
    // Called on the UI thread by InputLogic.
    public void updateTailBatchInput(final InputPointers batchPointers,
            final int sequenceNumber) {
        updateBatchInput(batchPointers, sequenceNumber, true /* isTailBatchInput */);
    }

    public void getSuggestedWords(final int inputStyle, final int sequenceNumber,
            final OnGetSuggestedWordsCallback callback) {
        synchronized (mLock) {
            if (mDestroyed) return;
            final Object session = mLatinIME.mEditorSession.capture();
            if (!mLatinIME.mEditorSession.isCurrent(session)) return;
            final SuggestionDecoder decoder = mLatinIME.captureSuggestionRequest(inputStyle, sequenceNumber);
            mNonUIThreadHandler.obtainMessage(
                    MSG_GET_SUGGESTED_WORDS, inputStyle, sequenceNumber,
                    new SuggestionRequest(session, decoder, callback)).sendToTarget();
        }
    }
}
