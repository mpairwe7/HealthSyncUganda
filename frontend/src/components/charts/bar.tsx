"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function SimpleBar<T extends Record<string, unknown>>({
  data,
  xKey,
  yKey,
  yLabel,
}: {
  data: T[];
  xKey: keyof T & string;
  yKey: keyof T & string;
  yLabel?: string;
}) {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey={xKey as string} stroke="#6b7280" fontSize={12} />
          <YAxis stroke="#6b7280" fontSize={12} label={{ value: yLabel ?? "", angle: -90, position: "insideLeft" }} />
          <Tooltip />
          <Bar dataKey={yKey as string} fill="#1f8a4c" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
