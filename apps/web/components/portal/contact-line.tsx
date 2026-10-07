import { channelLabel, type Channel } from "@/lib/format";

/** A buyer's email and phone as links, whether the email is proven, and how they may be
 * contacted. Shared by inquiries, holds and leads. */
export function ContactLine({
  email,
  phone,
  signedIn,
  contact,
}: {
  email: string;
  phone: string | null;
  signedIn: boolean;
  contact: Channel[];
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <a href={`mailto:${email}`} className="underline">
        {email}
      </a>
      {phone ? (
        <a href={`tel:${phone}`} className="underline">
          {phone}
        </a>
      ) : null}
      {signedIn ? null : <span className="text-muted-foreground">Email not verified</span>}
      <span className="text-muted-foreground">
        {contact.length > 0
          ? `Allows: ${contact.map(channelLabel).join(", ").toLowerCase()}`
          : "Reply only"}
      </span>
    </div>
  );
}
