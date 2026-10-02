"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Idaho spans Mountain (south) and Pacific (north) time; each subdivision stores its own.
const ZONES = [
  ["America/Boise", "Mountain: southern Idaho (America/Boise)"],
  ["America/Los_Angeles", "Pacific: northern Idaho (America/Los_Angeles)"],
  ["America/Denver", "Mountain (America/Denver)"],
  ["America/Phoenix", "Arizona (America/Phoenix)"],
  ["America/Chicago", "Central (America/Chicago)"],
  ["America/New_York", "Eastern (America/New_York)"],
  ["America/Anchorage", "Alaska (America/Anchorage)"],
  ["Pacific/Honolulu", "Hawaii (Pacific/Honolulu)"],
] as const;

export function TimeZoneSelect({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (zone: string) => void;
}) {
  const known = ZONES.some(([zone]) => zone === value);
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue placeholder="Choose a time zone" />
      </SelectTrigger>
      <SelectContent>
        {known || !value ? null : <SelectItem value={value}>{value}</SelectItem>}
        {ZONES.map(([zone, label]) => (
          <SelectItem key={zone} value={zone}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
