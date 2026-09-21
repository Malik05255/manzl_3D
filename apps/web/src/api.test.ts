import { describe,expect,it } from "vitest";
import { inferSourceMime } from "./api";

describe("source mime inference",()=>{
  it("uses a supported declared type",()=>{
    expect(inferSourceMime({name:"x.bin",type:"image/png"})).toBe("image/png");
  });
  it("falls back to file extension when Android omits type",()=>{
    expect(inferSourceMime({name:"house.PDF",type:""})).toBe("application/pdf");
    expect(inferSourceMime({name:"photo.JPEG"})).toBe("image/jpeg");
  });
  it("rejects unsupported extensions",()=>{
    expect(inferSourceMime({name:"plan.dwg",type:""})).toBeNull();
  });
});
