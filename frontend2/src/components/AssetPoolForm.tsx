/**
 * 资产池表单组件
 * 功能：用于创建和编辑资产池的表单
 * @param props 组件属性
 */
import { useState, useEffect } from 'react';

interface AssetPoolFormProps {
  initialData?: {
    id?: string;
    name: string;
    description: string;
  };
  onSubmit: (data: {
    id?: string;
    name: string;
    description: string;
  }) => void;
  onCancel: () => void;
}

const AssetPoolForm = (props: AssetPoolFormProps) => {
  const { initialData = { name: '', description: '' }, onSubmit, onCancel } = props;
  
  const [formData, setFormData] = useState({
    id: initialData.id,
    name: initialData.name,
    description: initialData.description
  });

  useEffect(() => {
    setFormData({
      id: initialData.id,
      name: initialData.name,
      description: initialData.description
    });
  }, [initialData]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    <div className="asset-pool-form-container">
      <h3>{formData.id ? '编辑资产池' : '创建资产池'}</h3>
      <form onSubmit={handleSubmit} className="asset-pool-form">
        <div className="form-group">
          <label htmlFor="name">资产池名称</label>
          <input
            type="text"
            id="name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            placeholder="请输入资产池名称"
          />
        </div>
        <div className="form-group">
          <label htmlFor="description">资产池描述</label>
          <textarea
            id="description"
            name="description"
            value={formData.description}
            onChange={handleChange}
            required
            placeholder="请输入资产池描述"
            rows={4}
          />
        </div>
        <div className="form-actions">
          <button type="button" className="btn-cancel" onClick={onCancel}>
            取消
          </button>
          <button type="submit" className="btn-submit">
            {formData.id ? '更新' : '创建'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AssetPoolForm;
