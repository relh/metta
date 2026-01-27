import { HeroLayout } from "@/components/HeroLayout";
import { S3_IMAGE_BASE } from "@/lib/constants";

import Frontpage from "./frontpage.mdx";

export const metadata = {
  title: "Softmax - Scaling alignment",
};

export default function Home() {
  return (
    <HeroLayout
      image={`${S3_IMAGE_BASE}/oscillon.png`}
      fade
      sentence="scaling alignment"
    >
      <Frontpage />
    </HeroLayout>

    /*
        document.addEventListener("DOMContentLoaded", function() {
          ScriptDecorator.init({
            sogidan: {
              fontSize: "24px",
              side: "left",
              lineHeight: "40px"
            }
          });
        });
    */
  );
}
