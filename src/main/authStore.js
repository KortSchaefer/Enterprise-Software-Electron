const fs = require("fs/promises");
const path = require("path");
const { app } = require("electron");

const AUTH_FILE_NAME = "auth-state.json";

function getAuthFilePath() {
  return path.join(app.getPath("userData"), AUTH_FILE_NAME);
}

async function readAuthState() {
  const filePath = getAuthFilePath();
  try {
    const content = await fs.readFile(filePath, "utf8");
    const parsed = JSON.parse(content);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (error) {
    if (error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

async function writeAuthState(nextState) {
  const filePath = getAuthFilePath();
  await fs.writeFile(filePath, JSON.stringify(nextState, null, 2), "utf8");
  return nextState;
}

async function clearAuthState() {
  const filePath = getAuthFilePath();
  try {
    await fs.unlink(filePath);
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }
}

module.exports = {
  readAuthState,
  writeAuthState,
  clearAuthState,
};
