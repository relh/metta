import { HeroLayout } from "@/components/HeroLayout";
import { S3_IMAGE_BASE } from "@/lib/constants";
import Research from "@/mdx/research.mdx";

export const metadata = {
  title: "Softmax - Inspiration",
};

export default function InspirationPage() {
  return (
    <HeroLayout
      image={`${S3_IMAGE_BASE}/gameoflife.png`}
      sentence="research that inspires us"
    >
      <Research />
    </HeroLayout>
  );
}
