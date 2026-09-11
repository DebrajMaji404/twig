/**
 * TypeScript definitions for Twig serialization codec.
 */

export interface TwigCodec {
  /**
   * Encodes a JSON-compatible object or array into compact Twig text.
   * @param data Single object or array of objects.
   * @returns Formatted Twig text string.
   */
  encode(data: any): string;

  /**
   * Decodes compact Twig text back into original JavaScript object or array.
   * @param text Twig text string.
   * @returns Reconstructed object or array.
   */
  decode(text: string): any;

  /**
   * Estimates subword token count for a text string using calibrated GPT-4o / Claude BPE rules.
   * @param text String to estimate tokens for.
   * @returns Approximate token count.
   */
  estimateTokens(text: string): number;
}

declare const Twig: TwigCodec;
export default Twig;

export const encode: (data: any) => string;
export const decode: (text: string) => any;
export const estimateTokens: (text: string) => number;
