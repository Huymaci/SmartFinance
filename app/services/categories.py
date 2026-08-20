from sqlalchemy import select, update

from app.extensions import db
from app.models import Alert, Budget, Category, Transaction
from app.repositories import CategoryRepository

from .common import ValidationError, owned_or_404, require_fields

NATURES = {"COMMITTED", "SEMI_FIXED", "DISCRETIONARY"}


def list_categories(user_id):
    return list(db.session.scalars(select(Category).where((Category.owner_id.is_(None)) | (Category.owner_id == user_id)).order_by(Category.parent_id, Category.name)))


def create(user, data):
    require_fields(data, "name", "nature")
    nature = str(data["nature"]).upper()
    if nature not in NATURES:
        raise ValidationError("nature không hợp lệ")
    parent_id = data.get("parent_id")
    if parent_id is not None:
        owned_or_404(CategoryRepository.available(int(parent_id), user.id))
    name = str(data["name"]).strip()
    if db.session.scalar(select(Category.id).where(Category.owner_id == user.id, Category.name == name)):
        raise ValidationError("Tên category đã tồn tại")
    category = Category(owner_id=user.id, parent_id=parent_id, name=name, nature=nature)
    db.session.add(category)
    db.session.commit()
    return category


def rename(user, category_id, name):
    category = db.session.scalar(select(Category).where(Category.id == category_id, Category.owner_id == user.id))
    owned_or_404(category)
    if not str(name or "").strip():
        raise ValidationError("Tên category không được trống")
    category.name = str(name).strip()
    db.session.commit()
    return category


def remove(user, category_id, reassign_to):
    category = owned_or_404(db.session.scalar(select(Category).where(Category.id == category_id, Category.owner_id == user.id)))
    target = owned_or_404(CategoryRepository.available(int(reassign_to), user.id))
    if target.id == category.id:
        raise ValidationError("Category thay thế phải khác category bị xóa")
    db.session.execute(update(Transaction).where(Transaction.category_id == category.id).values(category_id=target.id))
    existing_budget_keys = set(db.session.execute(select(Budget.month).where(Budget.user_id == user.id, Budget.category_id == target.id)).scalars())
    for budget in db.session.scalars(select(Budget).where(Budget.user_id == user.id, Budget.category_id == category.id)):
        if budget.month in existing_budget_keys:
            db.session.delete(budget)
        else:
            budget.category_id = target.id
    db.session.execute(update(Alert).where(Alert.user_id == user.id, Alert.category_id == category.id).values(category_id=target.id))
    db.session.delete(category)
    db.session.commit()
