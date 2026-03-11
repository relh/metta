import { redirect } from "next/navigation";

import { getLegacyJobRedirectHref } from "../utils";

export default async function JobPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  redirect(getLegacyJobRedirectHref(slug));
}
