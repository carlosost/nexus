/**
 * ReviewModal — Application Review opened as a popup from the Dashboard.
 *
 * Wraps ReviewApp in the shared Modal component so the user never has to
 * navigate away from the Dashboard to inspect a score or submit a review.
 *
 * Props:
 *   applicationId  {string | null}  UUID of the application to review.
 *                                   Falsy → modal is closed.
 *   onClose        {Function}       Called when the user closes the modal.
 */

import Modal     from './Modal.jsx';
import ReviewApp from './ReviewApp.jsx';

export default function ReviewModal({ applicationId, onClose }) {
  return (
    <Modal
      open={!!applicationId}
      onClose={onClose}
      title="Application Review"
      width="860px"
    >
      {applicationId && <ReviewApp applicationId={applicationId} />}
    </Modal>
  );
}
