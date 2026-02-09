/**
 * Pure utility functions for Agent Catalogue UI.
 * Zero dependencies - can be imported anywhere.
 * 
 * @module utils
 */

/**
 * Escape HTML special characters to prevent XSS attacks.
 * Converts characters that have special meaning in HTML to their entity equivalents.
 * 
 * @param {string} unsafe - Raw string that might contain HTML special characters
 * @returns {string} HTML-safe string with entities encoded
 * 
 * @example
 * escapeHtml('<script>alert("XSS")</script>')
 * // Returns: '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;'
 * 
 * @example
 * escapeHtml('Hello & goodbye')
 * // Returns: 'Hello &amp; goodbye'
 */
export function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') {
        return '';
    }
    
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
