import { Container } from "@/components/Container";

import PrivacyPolicy from "./privacy-policy.mdx";

export const metadata = {
  title: "Softmax - Privacy Policy",
};

export default function PrivacyPage() {
  return (
    <div className="flex w-full flex-col items-center">
      <div className="mt-8 mb-24 w-full max-w-[1200px] rounded-sm bg-[#fffdf4]">
        <Container>
          <PrivacyPolicy />
        </Container>
      </div>
    </div>
  );
}
