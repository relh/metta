import { redirect } from "next/navigation";

import { policiesRoute } from "@observatory/lib/routes";

export default function Home() {
  redirect(policiesRoute());
}
