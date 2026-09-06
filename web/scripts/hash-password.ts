import bcrypt from "bcryptjs";

/** Usage: npm run hash-password 'my great password' */
const pw = process.argv.slice(2).join(" ").trim();
if (!pw) {
  console.error("Usage: npm run hash-password '<password>'");
  process.exit(1);
}
console.log(bcrypt.hashSync(pw, 12));
