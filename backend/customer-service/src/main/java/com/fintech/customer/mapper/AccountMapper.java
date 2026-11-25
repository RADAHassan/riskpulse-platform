package com.fintech.customer.mapper;

import com.fintech.customer.domain.Account;
import com.fintech.customer.domain.CheckingAccount;
import com.fintech.customer.domain.SavingsAccount;
import com.fintech.customer.dto.AccountResponse;
import org.mapstruct.BeanMapping;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;
import org.mapstruct.SubclassMapping;

@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface AccountMapper {

    /** Aiguillage pur : aucun champ n'est mappe ici, seulement le choix de la methode selon le type reel. */
    @BeanMapping(ignoreByDefault = true)
    @SubclassMapping(source = CheckingAccount.class, target = AccountResponse.class)
    @SubclassMapping(source = SavingsAccount.class, target = AccountResponse.class)
    AccountResponse toResponse(Account account);

    @Mapping(target = "type", constant = "CHECKING")
    @Mapping(target = "interestRate", ignore = true)
    @Mapping(target = "minimumBalance", ignore = true)
    AccountResponse toResponse(CheckingAccount account);

    @Mapping(target = "type", constant = "SAVINGS")
    @Mapping(target = "overdraftLimit", ignore = true)
    AccountResponse toResponse(SavingsAccount account);
}