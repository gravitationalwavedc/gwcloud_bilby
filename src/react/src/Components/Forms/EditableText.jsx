import { HiOutlinePencil, HiOutlineCheck, HiOutlineX } from 'react-icons/hi';
import EdiText from 'react-editext';

const EditButton = () => (
    <>
        <HiOutlinePencil /> edit
    </>
);
const SaveButton = () => <HiOutlineCheck />;
const CancelButton = () => <HiOutlineX />;

const EditableText = ({ name, value, onSave, hint, viewProps, type, errors }) => (
    <>
        <EdiText
            type={type}
            name={name}
            value={value}
            viewProps={viewProps}
            onSave={onSave}
            hint={hint}
            editButtonContent={<EditButton />}
            editButtonClassName="edit-button"
            saveButtonContent={<SaveButton />}
            saveButtonClassName="save-button"
            cancelButtonContent={<CancelButton />}
            cancelButtonClassName="cancel-button"
            hideIcons
            editOnViewClick
            submitOnUnfocus
            submitOnEnter
        />
        {errors && <p className="text-danger small">{errors}</p>}
    </>
);

EditableText.defaultProps = {
    type: 'text',
};

export default EditableText;
