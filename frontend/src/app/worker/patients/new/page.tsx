"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { OfflineBanner } from "@/components/ui/offline-banner";
import { Select } from "@/components/ui/select";
import { useCreatePatient } from "@/lib/api/hooks";
import { useUi } from "@/lib/store/ui";

const UG_DISTRICTS = [
  "Kampala",
  "Wakiso",
  "Gulu",
  "Lira",
  "Mbarara",
  "Mbale",
  "Arua",
  "Jinja",
  "Kabale",
  "Hoima",
];

type Form = {
  nin: string;
  given_name: string;
  family_name: string;
  gender: "male" | "female" | "other" | "unknown";
  birth_date: string;
  phone: string;
  email: string;
  district: string;
  sub_county: string;
  parish: string;
  village: string;
  consent_to_share: boolean;
};

const initial: Form = {
  nin: "",
  given_name: "",
  family_name: "",
  gender: "female",
  birth_date: "",
  phone: "",
  email: "",
  district: UG_DISTRICTS[0]!,
  sub_county: "",
  parish: "",
  village: "",
  consent_to_share: true,
};

export default function NewPatientPage() {
  const [form, setForm] = useState<Form>(initial);
  const create = useCreatePatient();
  const pushToast = useUi((s) => s.pushToast);
  const router = useRouter();

  function update<K extends keyof Form>(k: K, v: Form[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const created = await create.mutateAsync({
        ...form,
        phone: form.phone || null,
        email: form.email || null,
        sub_county: form.sub_county || null,
        parish: form.parish || null,
        village: form.village || null,
      });
      pushToast({
        kind: "success",
        title: "Patient enrolled",
        description: `${form.given_name} ${form.family_name}`,
      });
      if (created && !created.id.startsWith("pending-")) {
        router.push(`/worker/patients/${created.id}`);
      } else {
        router.push("/worker/patients");
      }
    } catch (err) {
      pushToast({
        kind: "error",
        title: "Enrolment failed",
        description: (err as Error).message,
      });
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <OfflineBanner />
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Enrol new patient</h1>
        <p className="text-muted-foreground">
          The form works offline — data syncs when your connection returns.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Patient details</CardTitle>
          <CardDescription>
            All fields validated against NIRA conventions and Uganda district codes.
          </CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit}>
          <CardContent className="space-y-4">
            <Field label="National ID Number (NIN)">
              <Input
                required
                maxLength={14}
                value={form.nin}
                onChange={(e) => update("nin", e.target.value.toUpperCase())}
                placeholder="CMxxxxxxxxxxxx"
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Given name">
                <Input
                  required
                  value={form.given_name}
                  onChange={(e) => update("given_name", e.target.value)}
                />
              </Field>
              <Field label="Family name">
                <Input
                  required
                  value={form.family_name}
                  onChange={(e) => update("family_name", e.target.value)}
                />
              </Field>
              <Field label="Gender">
                <Select
                  value={form.gender}
                  onChange={(e) => update("gender", e.target.value as Form["gender"])}
                >
                  <option value="female">Female</option>
                  <option value="male">Male</option>
                  <option value="other">Other</option>
                  <option value="unknown">Unknown</option>
                </Select>
              </Field>
              <Field label="Date of birth">
                <Input
                  type="date"
                  required
                  value={form.birth_date}
                  onChange={(e) => update("birth_date", e.target.value)}
                />
              </Field>
              <Field label="Phone">
                <Input
                  type="tel"
                  inputMode="tel"
                  placeholder="+256 7xx xxx xxx"
                  value={form.phone}
                  onChange={(e) => update("phone", e.target.value)}
                />
              </Field>
              <Field label="Email (optional)">
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => update("email", e.target.value)}
                />
              </Field>
              <Field label="District">
                <Select
                  value={form.district}
                  onChange={(e) => update("district", e.target.value)}
                >
                  {UG_DISTRICTS.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Sub-county">
                <Input
                  value={form.sub_county}
                  onChange={(e) => update("sub_county", e.target.value)}
                />
              </Field>
              <Field label="Parish">
                <Input value={form.parish} onChange={(e) => update("parish", e.target.value)} />
              </Field>
              <Field label="Village">
                <Input value={form.village} onChange={(e) => update("village", e.target.value)} />
              </Field>
            </div>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={form.consent_to_share}
                onChange={(e) => update("consent_to_share", e.target.checked)}
              />
              <span>
                Citizen consents to share their record across MoH-accredited facilities
                for continuity of care. (Required by Uganda&apos;s Data Protection Act.)
              </span>
            </label>
            <Button type="submit" disabled={create.isPending} className="w-full">
              {create.isPending ? "Saving…" : "Enrol patient"}
            </Button>
          </CardContent>
        </form>
      </Card>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
