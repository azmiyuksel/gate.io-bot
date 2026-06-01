import { WalkForwardDetail } from "@/components/walkforward-detail";

export default function Page({ params }: { params: { id: string } }) {
  return <WalkForwardDetail id={params.id} />;
}
