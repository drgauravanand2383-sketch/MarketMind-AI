import { z } from "zod";

/** Shared by every route that can be reached via a redirect-with-return
 * (`/login`, `/unauthorized`) — where to send the user once they're
 * signed in again. */
export const redirectSearchSchema = z.object({ redirect: z.string().optional() });
export type RedirectSearch = z.infer<typeof redirectSearchSchema>;
