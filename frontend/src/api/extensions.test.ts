import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from './index';
import { extensionsApi } from './extensions';

vi.mock('./index', () => ({
  apiRequest: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const mockedGet = vi.mocked(apiRequest.get);
const mockedPost = vi.mocked(apiRequest.post);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('extensionsApi', () => {
  it('list 请求扩展列表', () => {
    void extensionsApi.list();
    expect(mockedGet).toHaveBeenCalledWith('/api/v1/extensions');
  });

  it('install 路径携带扩展 id', () => {
    void extensionsApi.install('rl');
    expect(mockedPost).toHaveBeenCalledWith('/api/v1/extensions/rl/install');
  });

  it('progress 路径携带扩展 id', () => {
    void extensionsApi.progress('rl');
    expect(mockedGet).toHaveBeenCalledWith('/api/v1/extensions/rl/progress');
  });

  it('uninstall 路径携带扩展 id', () => {
    void extensionsApi.uninstall('rl');
    expect(mockedPost).toHaveBeenCalledWith('/api/v1/extensions/rl/uninstall');
  });
});
